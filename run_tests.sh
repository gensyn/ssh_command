#!/bin/bash

coverage run --omit='test/*' -m unittest; coverage html
