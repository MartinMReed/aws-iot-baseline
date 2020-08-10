from aws_cdk import aws_cognito
from aws_cdk import aws_iot
from aws_cdk import aws_ssm
from aws_cdk import core

from baseline_cdk.util import cdk


def create_cognito(stack: core.Stack) -> None:
    cognito_scope: core.Construct = cdk.find_resource(stack, 'Cognito')
    user_pool: aws_cognito.CfnUserPool = cdk.find_resource(cognito_scope, 'UserPool')

    aws_ssm.CfnParameter(
        cognito_scope, 'UserPoolId',
        name=f'/{cdk.app_name}/cognito-pool-id',
        value=user_pool.ref,
        type='String'
    )

    aws_ssm.CfnParameter(
        cognito_scope, 'UserPoolUrl',
        name=f'/{cdk.app_name}/cognito-pool-url',
        value=f'https://cognito-idp.{stack.region}.amazonaws.com/{user_pool.ref}',
        type='String'
    )


def create_iot(stack: core.Stack) -> None:
    iot_scope: core.Construct = cdk.find_resource(stack, 'Iot')
    intermediate_policy: aws_iot.CfnPolicy = cdk.find_resource(iot_scope, 'IntermediatePolicy')
    standard_policy: aws_iot.CfnPolicy = cdk.find_resource(iot_scope, 'Policy')

    aws_ssm.CfnParameter(
        iot_scope, 'IntermediatePolicyName',
        name=f'/{cdk.app_name}/policy-intermediate',
        value=intermediate_policy.ref,
        type='String'
    )

    aws_ssm.CfnParameter(
        iot_scope, 'PolicyName',
        name=f'/{cdk.app_name}/policy',
        value=standard_policy.ref,
        type='String'
    )


def create_redis(stack: core.Stack) -> None:
    redis_scope: core.Construct = cdk.find_resource(stack, 'Redis')
    redis_cache_cluster: aws_iot.CfnPolicy = cdk.find_resource(redis_scope, 'CacheCluster')

    redis_address = aws_ssm.CfnParameter(
        redis_scope, 'EndpointAddress',
        name=f'/{cdk.app_name}/redis-address',
        value=redis_cache_cluster.get_att('RedisEndpoint.Address').to_string(),
        type='String'
    )

    redis_address.add_depends_on(redis_cache_cluster)

    redis_port = aws_ssm.CfnParameter(
        redis_scope, 'EndpointPort',
        name=f'/{cdk.app_name}/redis-port',
        value=redis_cache_cluster.get_att('RedisEndpoint.Port').to_string(),
        type='String'
    )

    redis_port.add_depends_on(redis_cache_cluster)


def create(stack: core.Stack) -> None:
    create_cognito(stack)
    create_iot(stack)
    create_redis(stack)

    aws_ssm.CfnParameter(
        stack, 'JwtIssuer',
        name=f'/{cdk.app_name}/jwt-issuer',
        value=cdk.app_name,
        type='String'
    )
