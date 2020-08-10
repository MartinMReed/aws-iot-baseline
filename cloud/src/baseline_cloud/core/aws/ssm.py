import typing

import boto3

from baseline_cloud.core.config import config

ssm_client = boto3.client('ssm')

parameters = {}


def get_parameter(name: str) -> typing.Union[str, typing.List[str]]:
    value = parameters.get(name)
    if not value:
        response = ssm_client.get_parameter(
            Name=f'/{config.app_name}/{name}',
            WithDecryption=True
        )
        value = response['Parameter']['Value']
        parameters[name] = value
    return value
