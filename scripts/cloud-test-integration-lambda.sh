#!/bin/bash

set -e

if [ -z "${AWS_LAMBDA_EVENT}" ]; then
  >&2 echo "Missing event value: AWS_LAMBDA_EVENT"
  exit 1
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
script_path=${script_dir}/$(basename "${BASH_SOURCE[0]}")
script_name=$(basename ${BASH_SOURCE[0]})

root_dir=$(cd "${script_dir}/.." && pwd)
cloud_dir=$(cd "${root_dir}/cloud" && pwd)
build_dir=${root_dir}/.build

function toolchain_require() { [ -n "$(command -v $1)" ] && return 0 || >&2 echo "$1: not found"; return 1; }
toolchain_require aws
toolchain_require python3
toolchain_require docker

function json_load() {
  python3 - <<-EOF
		import json
		with open('$1', 'r') as f:
		  j = json.load(f)
		  for path in '$2'.split('.'):
		    j = j.get(path)
		    if not j: break
		  if j: print(j)
	EOF
	return $?
}

app_name=$(json_load "${root_dir}/config.json" 'app_name')
topic_prefix=$(json_load "${root_dir}/config.json" 'topic_prefix')
lamba_type=ingest

rm -rf "${build_dir}/test"
mkdir -p "${build_dir}/test"
cd "${build_dir}/test"

python3 -m venv .venv
.venv/bin/pip3 install --quiet --upgrade pip
.venv/bin/pip3 install --quiet --upgrade setuptools
.venv/bin/pip3 install --quiet -r "${cloud_dir}/cdk/requirements.txt"

PYTHONPATH="${cloud_dir}/cdk" \
.venv/bin/python3 -u -B - <<-EOF

	lambda_type = '${lamba_type}'

	from baseline_cdk.util import cdk
	cdk.outdir = '$(pwd)'
	cdk.app_name = '${app_name}'
	cdk.topic_prefix = '${topic_prefix}'

	from baseline_cdk.resources import lambda_${lamba_type}
	lambda_${lamba_type}.create_layer_zip()
	lambda_${lamba_type}.create_lambda_zip()

EOF

unzip "${app_name}/lambda-${lamba_type}.zip" \
   -d "${app_name}/lambda-${lamba_type}-unpacked" > /dev/null

. "${root_dir}/cloud/scripts/aws-assume-role.sh" ${app_name}-lambda-${lamba_type}

if [[ "${AWS_ASSUMED_ROLE_ARN}" != *"/${app_name}-lambda-${lamba_type}/"* ]]; then
  printf "\nUnable to assume lambda role. Functionality may fail during test run.\n\n"
fi

docker container run                                                                  \
  -it                                                                                 \
  --rm                                                                                \
  --env AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}"                                      \
  --env AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}"                              \
  --env AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN}"                                      \
  --env USE_MOCK_REDIS="${USE_MOCK_REDIS}"                                            \
  --volume "$(pwd)/${app_name}/lambda-${lamba_type}-unpacked":/var/task:ro,delegated  \
  --volume "$(pwd)/${app_name}/lambda-${lamba_type}-layer":/opt:ro,delegated          \
  lambci/lambda:python3.8                                                             \
  "baseline_cloud.${lamba_type}.handler.handle" "${AWS_LAMBDA_EVENT}"