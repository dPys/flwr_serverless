import pickle
import time
from typing import Any
import boto3


class S3StorageBackend:
    def __init__(
        self, directory: str = None, retry_sleep_time: int = 3, max_retry: int = 3
    ):
        self.directory = directory
        if directory.startswith("s3://"):
            directory = directory[5:]
        parts = directory.split("/", 1)
        if len(parts) == 1:
            self.bucket = parts[0]
            self.prefix = None
        else:
            self.bucket = parts[0]
            self.prefix = parts[1].rstrip("/")
        self.suffix = ".pkl"
        self.retry_sleep_time = retry_sleep_time
        self.max_retry = max_retry
        self.s3 = boto3.client("s3")

    def _exists(self, key: str):
        results = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=key)
        return results["KeyCount"] > 0

    def get(self, key, default=None):
        success_flag_file = self._get_success_flag_file(key)
        patience = self.max_retry
        while not self._exists(success_flag_file):
            print(f"\nwaiting for success flag of {key}")
            time.sleep(self.retry_sleep_time)
            patience -= 1
            if patience == 0:
                return default
        if self.prefix is None:
            filepath = key + self.suffix
        else:
            filepath = self.prefix + "/" + key + self.suffix
        if self._exists(filepath):
            obj = self.s3.get_object(Bucket=self.bucket, Key=filepath)
            return pickle.loads(obj["Body"].read())
        else:
            return default

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value: Any):
        if self.prefix is None:
            filepath = key + self.suffix
        else:
            filepath = self.prefix + "/" + (key + self.suffix)
        if value is None:
            raise ValueError("value must not be None")
        self._delete_success_flag(key)
        self.s3.put_object(Bucket=self.bucket, Key=filepath, Body=pickle.dumps(value))
        self._put_success_flag(key)

    def _get_success_flag_file(self, key):
        if self.prefix is None:
            filepath = key + ".success"
        else:
            filepath = self.prefix + "/" + (key + ".success")
        return filepath

    def _delete_success_flag(self, key):
        filepath = self._get_success_flag_file(key)
        if self._exists(filepath):
            self.s3.delete_object(Bucket=self.bucket, Key=filepath)

    def _put_success_flag(self, key):
        filepath = self._get_success_flag_file(key)
        self.s3.put_object(Bucket=self.bucket, Key=filepath, Body=b"")

    def __len__(self):
        return len(self._list_pickle_files())

    def _list_pickle_files(self):
        filepaths = []
        res = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=self.prefix)
        for obj in res["Contents"]:
            if obj["Key"].endswith(self.suffix):
                filepaths.append(obj["Key"])
        return filepaths

    def items(self):
        for filepath in self._list_pickle_files():
            key_and_parameter = self.get_parameter(filepath)
            yield key_and_parameter

    def get_parameter(self, filepath):
        model_key = filepath.split("/")[-1].replace(self.suffix, "")
        return model_key, self.get(model_key)
