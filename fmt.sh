#!/bin/bash

isort -q .
black -q .
flake8 .
