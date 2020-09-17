#!/bin/bash

docker build --build-arg package="$(ls ./package)" -t tutorial_python_basic .
