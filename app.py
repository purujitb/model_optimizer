import glob
import json
import os
import subprocess
import tempfile

import requests
from celery import Celery
from flask import Flask, Response, request
from google.protobuf.json_format import MessageToDict, Parse
from google.protobuf.text_format import Merge, MessageToString
from minio import Minio
from minio.error import ResponseError

app = Flask(__name__)
celery = Celery(app.name, backend='rpc://', broker='amqp://')


class AuditEvents():
    SERVICE_LOADED = 100001
    OPTIMIZE_SERVICE_REQUEST_STARTED = 100002
    OPTIMIZE_SERVICE_REQUEST_COMPLETED = 100003
    OPTIMIZE_SERVICE_REQUEST_FAILED = 100004
    OPTIMIZE_SERVICE_REQUEST_QUEUED = 100005


JSON_CONTENT_TYPE = 'application/json'

optimize_cmd = [
    "python", "/opt/intel/openvino/deployment_tools/model_optimizer/mo.py"
]

minio_client = Minio('127.0.0.1:9000',
                     access_key='minioadmin',
                     secret_key='minioadmin',
                     secure=False)


def get_request_data_as_json():
    # Support both Content-Type and ContentType headers. ContentType because Coral and Content-Type because,
    # well, it is just the html standard
    input_content_type = request.headers.get(
        'ContentType', request.headers.get('Content-Type', JSON_CONTENT_TYPE))

    # utf-8 decoding is automatic in Flask if the Content-Type is valid. But that does not happens always.
    if input_content_type != JSON_CONTENT_TYPE:
        err_msg = "\nInvalid content type: {}. Supported content type(s): [{}]".format(
            input_content_type, JSON_CONTENT_TYPE)
        print(err_msg)

    content = request.get_data().decode('utf-8')

    # Content type changes for rest end points
    try:
        content_json = json.loads(content)
    except ValueError:
        if len(content) == 0:
            err_msg = "\nNo input body supplied in request"
        else:
            err_msg = "\nMalformed input body supplied in request: {}".format(
                content)
        print(err_msg)
        raise err_msg

    return content_json


@app.route('/optimize-model', methods=['POST'])
def optimize():
    print("\nAudit Event: {} Optimize Service Started".format(
        AuditEvents.OPTIMIZE_SERVICE_REQUEST_STARTED))
    # #### Get the request
    req_json = get_request_data_as_json()
    print(req_json)
    res = process.delay(req_json)

    print("\nThe task id is {}".format(res.id))

    print("\nAudit Event: {} Optimize Service Request Queued".format(
        AuditEvents.OPTIMIZE_SERVICE_REQUEST_QUEUED))

    return Response(status=200,
                    content_type=JSON_CONTENT_TYPE,
                    response=json.dumps({"taskID": res.id}))


@app.route('/get_status/<task_id>', methods=['GET'])
def get_status(task_id):
    task_status = celery.AsyncResult(task_id).state
    print("\nThe task_status is {}".format(task_status))

    return task_status


@celery.task
def process(req_json):
    cmd = optimize_cmd
    try:
        print(tempfile.tempdir, req_json['object_name'])
        tmp_path = os.path.join(tempfile.gettempdir(), req_json['object_name'])
        print("writing to {}".format(tmp_path))
        data = minio_client.get_object(bucket_name=req_json['bucket'],
                                       object_name=req_json['object_name'])

        with open(tmp_path, 'wb') as file_data:
            for d in data.stream(32 * 1024):
                file_data.write(d)
    except ResponseError as err:
        print(err)

    cmd.append('--input_model')
    cmd.append(tmp_path)
    for request_key in req_json:
        if request_key in ['bucket', 'object_name', 'output_location']:
            continue
        cmd.append('--' + request_key)
        cmd.append(req_json[request_key])

    cmd.append('--output_dir')
    cmd.append(tempfile.gettempdir())

    print("Using command: ", cmd)
    # ret = subprocess.run(cmd, shell=True)

    # try:
    #     op_file_pattern = os.path.splitext(tmp_path)[0] + "*"
    #     for op_file in glob.glob(op_file_pattern):
    #         with open(op_file, 'rb') as file_data:
    #             file_stat = os.stat(op_file)
    #             print(
    #                 minio_client.put_object(
    #                     bucket_name=req_json['bucket'],
    #                     object_name=os.path.basename(op_file),
    #                     data=file_data,
    #                     length=file_stat.st_size))
    # except ResponseError as err:
    #     print(err)

    # return ret


if __name__ == '__main__':
    app.run(debug=True)
