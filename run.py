#!/usr/bin/env python3
"""Test script to run and debug the main function"""
import sys
from twspace_dl.__main__ import main

# You can modify the arguments here to test different scenarios
# Example arguments:
# test_args = [
#     'twspace_dl',
#     '-h'  # Show help to see if main runs
# ]

# Uncomment and modify the below to test with actual parameters
test_args = [
    'twspace_dl',
    '-i', 'https://x.com/i/spaces/1mrxmPmvNgwJy',
    '-c', 'cookies.txt',
    '-v',  # verbose mode                                              \
]

# Set sys.argv to simulate command line arguments
sys.argv = test_args

# Run main
if __name__ == "__main__":
    exit_code = main()
    print(f"\nExited with code: {exit_code}")
