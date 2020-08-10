from aws_cdk import aws_s3
from aws_cdk import core

from baseline_cdk.resources import cfnres_str_random
from baseline_cdk.util import cdk


def create(stack: core.Stack) -> None:
    unique_id = cfnres_str_random.CfnStrRandom(
        stack, stack, 'BucketUniqueId',
        length=12
    )

    aws_s3.CfnBucket(
        stack, 'Bucket',
        bucket_name=f'{cdk.app_name}-{unique_id.ref}'
    )
