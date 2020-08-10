import os
import zipfile

from aws_cdk import aws_cloudformation
from aws_cdk import aws_iam
from aws_cdk import aws_lambda
from aws_cdk import aws_logs
from aws_cdk import core
from aws_cdk.core import RemovalPolicy

from baseline_cdk.util import cdk
from baseline_cdk.util.hash import file_sha1
from baseline_cdk.util.os import shell
from baseline_cdk.util.zip import exclude_pycache
from baseline_cdk.util.zip import zip_all

lambda_type = 'cfnres-iot-fleet'


def create_layer_zip() -> str:
    this_dir = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
    cloud_dir = os.path.abspath(f'{this_dir}/../../..')

    layer_dir = f'{cdk.outdir}/{cdk.app_name}/lambda-{lambda_type}-layer'
    layer_zip = f'{cdk.outdir}/{cdk.app_name}/lambda-{lambda_type}-layer.zip'

    if not os.path.exists(layer_dir):
        os.makedirs(layer_dir)

    shell(f'bash {cloud_dir}/scripts/aws-lambda-pip.sh'
          f'  -pyver 3.7'
          f'  -out "{layer_dir}/python/lib/python3.7/site-packages"'
          f'  -req "{this_dir}/cfnres/iot_fleet/requirements.txt"')

    with zipfile.ZipFile(layer_zip, 'w', zipfile.ZIP_DEFLATED) as zip:
        zip_all(zip, f'{layer_dir}', exclude_pycache, path='python')

    return layer_zip


def create_lambda_zip() -> str:
    this_dir = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))

    lambda_zip = f'{cdk.outdir}/{cdk.app_name}/lambda-{lambda_type}.zip'

    with zipfile.ZipFile(lambda_zip, 'w', zipfile.ZIP_DEFLATED) as zip:
        zip.write(f'{this_dir}/cfnres/iot_fleet/index.py', arcname='index.py')

    return lambda_zip


def create_lambda(stack: core.Stack, iot_scope: core.Construct) -> aws_lambda.CfnFunction:
    lambda_scope = core.Construct(iot_scope, 'FleetLambda')

    layer_zip = create_layer_zip()
    lambda_zip = create_lambda_zip()

    layer_asset = stack.synthesizer.add_file_asset(
        file_name=layer_zip,
        packaging=core.FileAssetPackaging.FILE,
        source_hash=file_sha1(layer_zip)
    )

    lambda_asset = stack.synthesizer.add_file_asset(
        file_name=lambda_zip,
        packaging=core.FileAssetPackaging.FILE,
        source_hash=file_sha1(lambda_zip)
    )

    lambda_role = aws_iam.CfnRole(
        lambda_scope, 'ExecutionRole',
        role_name=f'{cdk.app_name}-lambda-{lambda_type}',
        assume_role_policy_document={
            'Version': '2012-10-17',
            'Statement': [{
                'Effect': 'Allow',
                'Action': 'sts:AssumeRole',
                'Principal': {
                    'Service': 'lambda.amazonaws.com',
                    **({'AWS': f'arn:aws:iam::{stack.account}:root'} if cdk.debug_lambda_roles else {})
                }
            }]
        },
        managed_policy_arns=[
            'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
        ],
        policies=[aws_iam.CfnRole.PolicyProperty(
            policy_name=f'{cdk.app_name}-lambda-{lambda_type}',
            policy_document={
                'Version': '2012-10-17',
                'Statement': [{
                    'Effect': 'Allow',
                    'Action': [
                        'iot:UpdateCertificate',
                        'iot:DeleteCertificate',
                        'iot:DeleteThing',
                        'iot:ListAttachedPolicies',
                        'iot:DetachPolicy',
                        'iot:ListThingPrincipals',
                        'iot:DetachThingPrincipal',
                        'iot:ListThings',
                        'iot:ListPrincipalThings',
                        'iot:ListTagsForResource',
                        'events:PutRule',
                        'events:DeleteRule',
                        'events:PutTargets',
                        'events:RemoveTargets',
                        'lambda:AddPermission',
                        'lambda:RemovePermission'
                    ],
                    'Resource': '*'
                }]
            }
        )]
    )

    lambda_layer = aws_lambda.CfnLayerVersion(
        lambda_scope, 'Layer',
        layer_name=f'{cdk.app_name}-{lambda_type}',
        compatible_runtimes=['python3.7'],
        content=aws_lambda.CfnLayerVersion.ContentProperty(
            s3_bucket=layer_asset.bucket_name,
            s3_key=layer_asset.object_key
        )
    )

    lambda_function = aws_lambda.CfnFunction(
        lambda_scope, 'Function',
        function_name=f'{cdk.app_name}-{lambda_type}',
        runtime='python3.7',
        code=aws_lambda.CfnFunction.CodeProperty(
            s3_bucket=lambda_asset.bucket_name,
            s3_key=lambda_asset.object_key
        ),
        handler='index.handle',
        layers=[lambda_layer.ref],
        memory_size=128,
        timeout=600,
        role=lambda_role.attr_arn
    )

    lambda_function.add_depends_on(lambda_role)

    lambda_log_group = aws_logs.CfnLogGroup(
        lambda_scope, 'LogGroup',
        log_group_name=f'/aws/lambda/{lambda_function.ref}',
        retention_in_days=7,
    )

    lambda_log_group.apply_removal_policy(policy=RemovalPolicy.DESTROY)

    return lambda_function


def create(stack: core.Stack) -> None:
    iot_scope: core.Construct = cdk.find_resource(stack, 'Iot')

    lambda_function = create_lambda(stack, iot_scope)

    custom_resource = aws_cloudformation.CfnCustomResource(
        iot_scope, 'Fleet',
        service_token=lambda_function.attr_arn
    )
    custom_resource.add_override('Type', 'Custom::IotFleet')
    custom_resource.add_override('Properties.ThingTypeName', cdk.app_name)
    custom_resource.add_override('Properties.ThingRemovalPolicy', RemovalPolicy.DESTROY)

    custom_resource.add_depends_on(lambda_function)

    # make sure this runs first when destroying the stack
    for child in iot_scope.node.children:
        if isinstance(child, core.CfnResource):
            custom_resource.add_depends_on(child)
