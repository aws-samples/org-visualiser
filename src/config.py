# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import argparse
import logging
import re 
from datetime import datetime, date

def json_serialise(obj):
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d, %H:%M:%S %Z")
    elif isinstance(obj, date):
        return obj.strftime("%Y-%m-%d %Z")
    else:
        raise TypeError (f"Type {type(obj)} not serializable")


#Reference: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html

def regex_validator_generator(regex, desc_param_name, custom_message = ""):
    pattern = re.compile(regex)
    def regex_validator(arg_value):
        if not pattern.match(arg_value):
            raise argparse.ArgumentTypeError(f"Invalid {desc_param_name}. {custom_message}")
        return arg_value
    return regex_validator

def maxlen_validator_generator(max_len, desc_param_name):
    def maxlen_validator(arg_value):
        if len(arg_value) > max_len:
            raise argparse.ArgumentTypeError(f"{desc_param_name} too long. It should not exceed {max_len} characters.")
        return arg_value
    return maxlen_validator

def log_func(func):
    def inner(*args, **kwargs):
        logging.debug(f"Entering {func.__name__}")
        result = func(*args, **kwargs)
        logging.debug(f"Leaving {func.__name__}")
        return result
    return inner

#Define the arguments
parser = argparse.ArgumentParser(description='Generate AWS Account/Org structure visualizations')
parser.add_argument('-d', '--depth', metavar='depth', choices = ['ou','account'],
                    help='Indicate if the depth should be only upto the "ou" or all the way to the "account" level. Default is "account"',
                    default = 'account')
parser.add_argument('-o', '--output', metavar='output_file_name', dest='output_file_name',
                    default='output/output.html',
                    type=regex_validator_generator(regex = r".+\.html+$", desc_param_name = "Output file name", custom_message = "Please make sure it ends with '.html'"),
                    help='Name of the html file to which the output will be written to (you can include the path too. Either relative to the current folder or the absolute path). Please include the suffix ".html" in the filename. Default is output/output.html')
parser.add_argument('--dark-mode', action='store_true', dest='dark_mode',
                    default=False,
                    help="Use this option if you want the visualization with a black background. Default is False")
parser.add_argument('--aws-profile', metavar='aws_profile_name', dest='aws_profile_name',
                    default=None,
                    type=maxlen_validator_generator(max_len = 250,desc_param_name = "AWS Profile name"),
                    help="Use this option if you want to pass in an AWS profile already congigured for the CLI")
parser.add_argument('--aws-assume-role', metavar='aws_assume_role_name', dest='aws_assume_role_name',
                    default=None,
                    type=regex_validator_generator(regex = r"^[a-zA-Z0-9+=,.@_-]+$", desc_param_name = "IAM Role name"),
                    #type=iam_entity,
                    help="Use this option if you want the aws profile to assume a role before querying Org related information")
parser.add_argument('--show-options', action='store_true', dest='show_options',
                    default=False,
                    help="Use this option if you want the graph visualisation options on the visualisation html. This will allow you to try out many different possibilities (for example, showing the graph as a hierarchy). Default is False")
parser.add_argument('--log-level', metavar='log_level', dest='log_level',
                    default='ERROR', choices = ['DEBUG','INFO','WARNING','ERROR','CRITICAL'],
                    help="Log level. Needs to be one of the following: 'DEBUG','INFO','WARNING','ERROR','CRITICAL'")
args = parser.parse_args()

#Set up logging
logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=args.log_level,
    datefmt='%Y-%m-%d %H:%M:%S')

#Set up visualization options based on arguments
if args.dark_mode:
    OU_color = 'blue'
    account_color = 'lime'
    payer_account_color = 'red'
    other_account_color = 'yellow'
    root_OU_color = 'white'
    OU_colors = ['white','coral','cyan','bisque', 'darkkhaki', 'cadetblue', 'coral']
    bgcolor = 'black'
    font_color = 'white'
else:
    OU_color = 'blue'
    account_color = 'lime'
    payer_account_color = 'red'
    other_account_color = 'yellow'
    root_OU_color = 'black'
    OU_colors = ['white','coral','cyan','bisque', 'darkkhaki', 'cadetblue', 'coral']
    bgcolor = 'white'
    font_color = 'black'

root_OU_size = 5
OU_shape = 'star' #Refer to the "shape" parameter in the add_node function here for possible options - https://pyvis.readthedocs.io/en/latest/documentation.html#pyvis.network.Network.add_node
account_shape = 'dot'
#Expose args members to other modules
output_file_name = args.output_file_name
dark_mode = args.dark_mode
show_options = args.show_options
depth = args.depth
log_level = args.log_level
aws_profile_name = args.aws_profile_name
aws_assume_role_name = args.aws_assume_role_name

directed = False #Indicates if the visualization shows arrows at the end of edges
