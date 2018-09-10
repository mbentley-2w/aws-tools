#!/bin/bash
#
# Prereq:
#
#    brew install jq
#
# Or Download from here:
#
#    https://stedolan.github.io/jq/download/

for quoted_func in $(aws lambda list-functions | jq ".Functions[].FunctionName"); do
    func=$(sed -e 's/^"//' -e 's/"$//' <<<"$quoted_func")
    quoted_url=$(aws lambda get-function --function-name $func | jq '.Code.Location')
    url=$(sed -e 's/^"//' -e 's/"$//' <<<"$quoted_url")
    curl -o ${func}.zip $url
done

