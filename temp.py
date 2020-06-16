from minio import Minio
import os

minio_client = Minio('127.0.0.1:9000',
                     access_key='minioadmin',
                     secret_key='minioadmin',
                     secure=False)

if __name__ == "__main__":
    op_file = '/home/ubuntu/frozen.pb'
    with open(op_file, 'rb') as file_data:
        file_stat = os.stat(op_file)
        print(
            minio_client.put_object(
                bucket_name='model-optimizer',
                object_name='frozen.pb',
                data=file_data,
                length=file_stat.st_size))