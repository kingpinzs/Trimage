#!/usr/bin/env python3
#
# Copyright (c) 2010 Kilian Valkhof, Paul Chaplin, Tarnay Kalman
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

import os
import sys

# Ensure the trimage package directory is on the path
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from trimage.trimage import main

if __name__ == "__main__":
    main()
