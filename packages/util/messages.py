import base64
import time
import os
import json
import pip
import zlib
from nimbella import redis

def main(args):
    body = args["__ow_body"]
    if args["__ow_headers"]["content-type"] == "application/json":
        body = base64.b64decode(body).decode("utf-8")
    body = json.loads(body)

    if ( body.get("fiscal_code") and 
         body.get("content") and
         body.get("content").get("subject") and
         body.get("content").get("markdown") and
         body.get("content").get("due_date") ):
            code = body["fiscal_code"]
            id = str(zlib.crc32(code.encode("utf-8")))
            red = redis()
            data = json.dumps(body).encode("utf-8")
            red.set("message:%s" % code, data)
            return {"body": {"id": id} }

    return { "body": { "detail": "validation errors"}}


