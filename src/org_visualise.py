# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import networkx as nx
from pyvis.network import Network
import config
import os
import json
import copy

from config import log_func
from config import logging


class OrgVisualiser:
    #Contain the accounts and OUs in an array of dicts. Each dict will represent an account or an OU
    nodes = []

    #A graph that contains the nodes and their parent-child relationships. This will be built out of the nodes array above.
    G = nx.DiGraph()

    #Boto3 client that will be used by mutiple methods.
    org_client = None

    def __init__(self): #If a role is passed then use that role to get the session
        session = boto3.Session(profile_name = config.aws_profile_name)

        if config.aws_assume_role_name: #Need to assume a role before creating an org client

            sts_client = session.client('sts')
            account_id = sts_client.get_caller_identity()["Account"]

            assumed_role_object=sts_client.assume_role(
                RoleArn=f"arn:aws:iam::{account_id}:role/{config.aws_assume_role_name}",
                RoleSessionName="AssumeRoleForOrgVis"
            )
            credentials=assumed_role_object['Credentials']

            role_session = boto3.Session(
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
            )
            org_session = role_session #Use this new session as the one for org API calls
        else:
            org_session = session #Since no role was passed, the original session itself is used for org API calls

        self.org_client = org_session.client('organizations')
        self.get_root_id()

    #This method is the key that lays out in what sequence the rest of the methods of this class are invoked.
    @log_func
    def generate_visualisation(self):
        #Get necessary information from AWS APIs
        self.nodes.append({'Id':self.root_id, 'Type':'ROOT', 'ParentId':None})
        self.add_descendents(self.root_id)
        self.update_node_attributes()
        
        #Create Digraph and update the label of each node to add count of accounts under each OU
        self.create_graph()
        self.update_ou_counts()

        #Check if the visualisation is needed at the OU level and if so, delete the accounts
        if config.depth == 'ou':
            self.delete_accounts_from_graph()

        #Plot the network
        self.plot_network()

    @log_func
    def get_root_id(self):
        roots = self.org_client.list_roots()
        logging.info("Setting root id as " + roots['Roots'][0]['Id'])
        self.root_id = roots['Roots'][0]['Id']

    @log_func
    #This is a recursive function that keeps digging deeper until it reachest the leaf OUs and adds the OUs to the nodes[] list. This function is invoked once for every OU.
    #Once child OUs are found, the child accounts are added to the nodes[] list
    def add_descendents(self, parent_id, depth = 0):
        children = []

        #First get OUs and keep recursing until you reach the leaf OU
        response = self.org_client.list_children(ParentId=parent_id, ChildType = 'ORGANIZATIONAL_UNIT')
        for child in response['Children']:
            self.nodes.append({'Id':child['Id'], 'Type':'ORGANIZATIONAL_UNIT', 'ParentId':parent_id, 'Depth' : depth+1})
            self.add_descendents(child['Id'], depth+1)
        #Check for any NextToken values and if so, fetch more child OUs
        while ('NextToken' in response):
            children = self.org_client.list_children(ParentId=parent_id, ChildType = 'ORGANIZATIONAL_UNIT', NextToken = children['NextToken'])
            for child in children['Children']:
                self.nodes.append({'Id':child['Id'], 'Type':'ORGANIZATIONAL_UNIT', 'ParentId':parent_id, 'Depth' : depth+1})
                self.add_descendents(child['Id'], depth+1)
        
        #Then get the accounts for the OU
        response = self.org_client.list_children(ParentId=parent_id, ChildType = 'ACCOUNT')
        for child in response['Children']:
            self.nodes.append({'Id':child['Id'], 'Type':'ACCOUNT', 'ParentId':parent_id, 'Depth' : depth+1})
        #Check for any NextToken values and if so, fetch more child accounts
        while ('NextToken' in response):
            children = self.org_client.list_children(ParentId=parent_id, ChildType = 'ACCOUNT', NextToken = children['NextToken'])
            for child in children['Children']:
                self.nodes.append({'Id':child['Id'], 'Type':'ACCOUNT', 'ParentId':parent_id, 'Depth' : depth+1})

    @log_func
    #Update attributes like OU Name, Account Name, Account Status, Management Account Id etc.
    def update_node_attributes(self):
        for node in self.nodes:
            if node['Type'] == 'ORGANIZATIONAL_UNIT':
                response = self.org_client.describe_organizational_unit(OrganizationalUnitId = node['Id'])
                ou_name = response['OrganizationalUnit']['Name']
                node['Name'] = ou_name
                node['color'] = config.OU_colors[node['Depth']]
                node['shape'] = config.OU_shape
                node['title'] = json.dumps(response['OrganizationalUnit'],  default = config.json_serialise, indent = 4)
            elif node['Type'] == 'ACCOUNT':
                response = self.org_client.describe_account(AccountId = node['Id'])
                node['Name'] = response['Account']['Name']
                node['Status'] = response['Account']['Status']
                node['color'] = config.account_color
                node['shape'] = config.account_shape
                print(str(response['Account']))
                node['title'] = json.dumps(response['Account'],  default = config.json_serialise, indent = 4)
            else: #Root
                org = self.org_client.describe_organization()
                mgmt_account_id = org['Organization']['MasterAccountId']
                response = self.org_client.describe_account(AccountId = mgmt_account_id)
                node['MgmtAccountId'] = mgmt_account_id
                node['MgmtAccountName'] = response['Account']['Name']
                node['Name'] = 'Root' + '-' + node['MgmtAccountName']
                node['color'] = config.root_OU_color
                node['shape'] = config.OU_shape
                node['value'] = config.root_OU_size
                node['title'] = json.dumps(response['Account'],  default = config.json_serialise, indent = 4)
            node['label'] = node['Name']


    @log_func
    def create_graph(self):

        #Add nodes
        for node in self.nodes:
            self.G.add_node(node['Id'], **node)

        #Add edges
        for node in self.nodes:
            if node['ParentId']:
                self.G.add_edge(node['ParentId'], node['Id'])

    #This has to run on the Graph and not on the original Dict because it uses the dfs traversal
    #This function counts the number of descendent accounts for each OU and adds it to the "label" attribute of the node.
    @log_func
    def update_ou_counts(self):
        for n in list(self.G.nodes):
            if (self.G.nodes[n])['Type'] in ['ORGANIZATIONAL_UNIT', 'ROOT']:
                descendents_acct_count = self.get_descendent_accounts_count(n)
                (self.G.nodes[n])['label'] = (self.G.nodes[n])['label'] + '(' + str(descendents_acct_count)+ ')'
                (self.G.nodes[n])['DescendentAccountsCount'] = descendents_acct_count

    #This counts for all descendents that are accounts
    @log_func
    def get_descendent_accounts_count(self, n):
        descendents = list(nx.dfs_preorder_nodes(self.G,n))
        acc_count = 0
        for n in descendents:
            if (self.G.nodes[n])['Type'] == 'ACCOUNT':
                acc_count = acc_count + 1
        return acc_count

    @log_func
    def plot_network(self):
        nt = Network('1000px', '1900px',
            bgcolor = config.bgcolor,
            font_color = config.font_color,
            directed = config.directed)

        nt.from_nx(self.G)
        if config.show_options:
            nt.show_buttons()
        
        os.makedirs(os.path.dirname(config.output_file_name), exist_ok=True)
        nt.show(config.output_file_name)

    @log_func
    #This will be used if the visualisation depth is limited to OUs. The accounts have to be added and *then* removed, because after the accounts are added, that information is used for calculating descendent counts, after which the accounts can be deleted if not needed.
    def delete_accounts_from_graph(self):
        for n in list(self.G.nodes):
            if (self.G.nodes[n])['Type'] == 'ACCOUNT':
                self.G.remove_node(n)

#End of class OrgVisualiser

#Main
OV = OrgVisualiser()
OV.generate_visualisation()
