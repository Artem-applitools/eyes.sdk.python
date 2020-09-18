#!/bin/bash
set -e
DIR=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )
cd $DIR
$DIR/build.sh

docker run -e APPLITOOLS_API_KEY tutorial_python_basic
docker run -e APPLITOOLS_API_KEY tutorial_python_ufg

$DIR/report.sh