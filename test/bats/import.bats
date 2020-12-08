#!/usr/bin/env bats
load util

@test "util/import" {
   ipost $URL/util/import
   ckline '"name": "url"'
   ckline '"name": "username"'
   ckline '"name": "password"'
   ckline '"name": "jsonargs"'
   ckline '"name": "useget"'
}

@test "util/import get" {
   ipost $URL/util/import useget=true url=https://raw.githubusercontent.com/pagopa/io-sdk/master/docs/sample.json
   ckline '"fiscal_code": "AAAAAA00A00A000A"'
   ckline '"markdown":'
   ckline '"subject":'
}

@test "util/import sample get" {
  ipost $URL/util/import useget=true url="$SAMPLE"
  ckline '"AAAAAA00A00A000A:1"'
  ckline '"markdown"'
  ckline '"subject"'
  ipost $URL/util/import useget=true url="$SAMPLE?count=2"
  ckline '"AAAAAA00A00A000A:2"'
  ipost $URL/util/import useget=true url="$SAMPLE?fiscal_code=BBBBB00B00B000B"
  ckline '"BBBBB00B00B000B:1"'
}

@test "util/import sample post" {
   ipost $URL/util/import url="$SAMPLE"
   ckline '"fiscal_code": "AAAAAA00A00A000A:1"'
   ckline '"markdown":'
   ckline '"subject":'
}

@test "util/import sample post with args" {
   ijpost $URL/util/import url="$SAMPLE/util/sample" jsonargs='{"count":2,"fiscal_code":"BBBBB00B00B000B","amount":1,"due_date":"2021-01-01"}'
   ckline '"BBBBB00B00B000B:2"'
   ckline '"amount": 1'
   ckline '"due_date": "2021-01-01T00:00:00"'
}
