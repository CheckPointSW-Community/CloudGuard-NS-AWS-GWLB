"""
Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

AWS Disclaimer.

(c) 2019 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.
This AWS Content is provided subject to the terms of the AWS Customer
Agreement available at https://aws.amazon.com/agreement/ or other written
agreement between Customer and Amazon Web Services, Inc.

Looks up VPC and associated subnets based on tags.
Returns the VPC and Subnet values back to the custom resource.

Runtime: python3.8
Last Modified: 6/11/2021 by chkp-jeffkopko
"""

from __future__ import print_function
from botocore.exceptions import ClientError
import boto3
import json
import logging
import os
import urllib3
import time


EC2_CLIENT = boto3.client('ec2')
IAM_CLIENT = boto3.client('iam')

SUCCESS = "SUCCESS"
FAILED = "FAILED"
http = urllib3.PoolManager()


def lambda_handler(event, context):
    response_data = {}
    setup_logging()
    log.info('In Main Handler')
    log.info(json.dumps(event))
    print(json.dumps(event))

    account = event['ResourceProperties']['Account']
    region = event['ResourceProperties']['Region']
    vpc_tags = event['ResourceProperties']['Vpc_Tags']
    cidr = event['ResourceProperties']['CIDR']
    tgw_id = event['ResourceProperties']['tgw_id']
    sec_vpc_id = event['ResourceProperties']['sec_vpc_id']
    inet_vpc_id = event['ResourceProperties']['inet_vpc_id']
    sec_subnets = event['ResourceProperties']['sec_subnets']
    inet_subnets = event['ResourceProperties']['inet_subnets']

    if event['RequestType'] in ['Update', 'Create']:
        log.info('Event = ' + event['RequestType'])

        #create attachments for sec & inet VPC's and record their ID's
        sec_attach_id  = create_tgw_attachment(tgw_id, sec_vpc_id, sec_subnets, True)
        inet_attach_id = create_tgw_attachment(tgw_id, inet_vpc_id, inet_subnets, False)

        #create RT for egress and ingress
        egress_rt = create_tgw_rt(tgw_id, "tgw-egress", False)
        ingress_rt = create_tgw_rt(tgw_id, "tgw-ingress", True)

        #create RT routes
        create_tgw_rt_route(ingress_rt, "0.0.0.0/0", sec_attach_id)
        # duplicate as needed for all spokes to propagate routes
        create_tgw_rt_propagate(egress_rt, inet_attach_id)
        create_tgw_rt_route(egress_rt, "0.0.0.0/0", inet_attach_id)

        #associate RT to attachments
        create_tgr_rt_assoc(egress_rt, sec_attach_id)
        #duplicate this as needed for all spokes
        create_tgr_rt_assoc(ingress_rt, inet_attach_id)

        #TO DO
            #attach spokes
            #add Spoke Routes to agress RT
            #modify Spoke VPC RT to point to TGW
            #add spoke routes to Inet VPC NATGW Subnet RT


        # spoke route attachments
        #create_service_link_role()
        vpc_metadata = get_vpc_metadata(account, region, vpc_tags, cidr)
        create_transit_gateway_spoke_attachments(vpc_metadata, tgw_id, egress_rt, ingress_rt)
        create_vpc_route_to_tgw(vpc_metadata, tgw_id, cidr)

        #send(event, context, 'SUCCESS', response_data)

    else:
        log.error("failed to run")
        send(event, context, 'FAILED', response_data)

    if event['RequestType'] in ['Delete']:
        log.info('Event = ' + event['RequestType'])

        send(event, context, 'SUCCESS', response_data)

def create_tgw_attachment(tgw_id, vpc_id, subnets, appliance):

    data = {
            "TransitGatewayId": tgw_id,
            "VpcId": vpc_id,
            "SubnetIds": subnets,
    }

    if appliance:
        data["Options"] = {"ApplianceModeSupport":"enable"}
        data["TagSpecifications"]= [
                {
                    "ResourceType": "transit-gateway-attachment",
                    "Tags": [ {"Key":"Name", "Value": "SecurityVPCAttachment"},]
                }
            ]
    else:
        data["TagSpecifications"]= [
                {
                    "ResourceType": "transit-gateway-attachment",
                    "Tags": [{"Key": "Name", "Value": "InternetVPCAttachment"}, ]
                }
            ]
    try:
        response = EC2_CLIENT.create_transit_gateway_vpc_attachment(**data)
        ("CREATED TGW Attachment for  VPC: " + vpc_id + " with attachment ID: " + response["TransitGatewayVpcAttachment"]["TransitGatewayAttachmentId"])
    except Exception as e:
        log.info("Error creating TGW Attach for " + vpc_id)
        log.error(e)
        return None

    time.sleep(90)

    return response["TransitGatewayVpcAttachment"]["TransitGatewayAttachmentId"]

def create_tgw_rt(tgw_id, name, default_rt):

    try:
        response = EC2_CLIENT.create_transit_gateway_route_table(
            TransitGatewayId=tgw_id,
            TagSpecifications= [
                {
                    "ResourceType": "transit-gateway-route-table",
                    "Tags": [
                        {
                            "Key": "Name",
                            "Value": name,
                        },
                    ]
                },
            ]
        )
        log.info("CREATED TGW RT VPC: " + name + " with ID: " + response["TransitGatewayRouteTable"]["TransitGatewayRouteTableId"])
    except Exception as e:
        log.info("Error creating TGW RT " + name)
        log.error(e)
        return None

    return response["TransitGatewayRouteTable"]["TransitGatewayRouteTableId"]

def create_tgw_rt_route (tgw_rt, cidr, attach_id):
    try:
        response = EC2_CLIENT.create_transit_gateway_route(
            DestinationCidrBlock=cidr,
            TransitGatewayRouteTableId=tgw_rt,
            TransitGatewayAttachmentId=attach_id,
        )
        log.info("CREATED TGW Route in RT: " + tgw_rt  + " for " + CIDR)
    except Exception as e:
        log.info("Error creating route for RT: " + tgw_rt + " with attachment: " + attach_id)
        log.error(e)
        return None

def create_tgw_rt_propagate(tgw_rt, attach_id):
    try:
        response = EC2_CLIENT.enable_transit_gateway_route_table_propagation(
            TransitGatewayRouteTableId=tgw_rt,
            TransitGatewayAttachmentId=attach_id,
        )
    except Exception as e:
        log.info("Error creating propagate for attachment: " + attach_id)
        log.error(e)
        return None

def create_tgr_rt_assoc(tgw_rt, attach_id):
    try:
        response = EC2_CLIENT.associate_transit_gateway_route_table(
            TransitGatewayRouteTableId=tgw_rt,
            TransitGatewayAttachmentId=attach_id,
        )
    except Exception as e:
        log.info("Error creating RT assoc for RT: " + tgw_rt + "with attachment: " + attach_id)
        log.error(e)
        return None

def create_transit_gateway_spoke_attachments(vpc_metadata, tgw_id, egress_rt, ingress_rt):
    for entry in vpc_metadata:
        if entry['Subnet']:
            try:
                attach_name = entry['Vpc'] + "Attachment"
                data = {
                    "TransitGatewayId": tgw_id,
                    "VpcId": entry['Vpc'],
                    "SubnetIds": entry['Subnet']
                    "TagSpecifications" : [
                        {
                        "ResourceType": "transit-gateway-attachment",
                        "Tags": [{"Key": "Name", "Value": attach_name}, ]
                        }
                    ]
                }

                response = EC2_CLIENT.create_transit_gateway_vpc_attachment(**data)

                new_attach_id = response["TransitGatewayVpcAttachment"]["TransitGatewayAttachmentId"]

                time.sleep(90)

                #add Spoke VPC Propagation to TGW Egress RT
                create_tgw_rt_propagate(egress_rt, new_attach_id)

                #associate ingress RT with newly created spoke attachment
                create_tgr_rt_assoc(ingress_rt, new_attach_id)

                log.info ("created new TGW attachment for VPC: " + entry['Vpc'] + "with attach ID: " + new_attach_id)
                log.info ("forced inspection through Check Point Security VPC")

            except Exception as e:
                log.error(e)
                return None
        else:
            print('No subnets in VPC,' + entry['Vpc'] +' unable to attach VPC')

def get_vpc_metadata(account, region, vpc_tags, cidr):
    vpc_tags = vpc_tags.replace(' ','')
    vpc_tags = vpc_tags.split(',')

    returned_metadata = []

    for tag in vpc_tags:
        try:
            get_vpc_response = EC2_CLIENT.describe_vpcs()
            for vpc in get_vpc_response['Vpcs']:
                if 'Tags' in vpc:
                    for tag_value in vpc['Tags']:
                        if tag_value['Value'] == tag:
                            metadata = {}
                            returned_vpc = vpc['VpcId']
                            subnets = get_subnets(returned_vpc)
                            route_table = get_default_route_table(returned_vpc,cidr)
                            metadata['Vpc'] = returned_vpc
                            metadata['Subnet'] = subnets
                            metadata['Route_Table'] = route_table
                            metadata['Cidr'] = vpc['CidrBlock']
                            returned_metadata.append(metadata)

        except Exception as e:
            log.error(e)
            return None


    return returned_metadata


def get_subnets(returned_vpc):
    subnet_list = []
    az_subnet_mapping = []

    try:
        get_subnet_response = EC2_CLIENT.describe_subnets(
            Filters=[
                {
                    'Name': 'vpc-id',
                    'Values': [returned_vpc]
                }])

        for entry in get_subnet_response['Subnets']:
            subnet_list.append(entry['SubnetId'])

        for subnet in subnet_list:
            response = EC2_CLIENT.describe_subnets(
                Filters=[
                    {
                        'Name': 'subnet-id',
                        'Values': [subnet]
                    },
                ],
            )

            for sub in response['Subnets']:
                if not any(sub['AvailabilityZone'] in az for az in az_subnet_mapping):
                    az_subnet_mapping.append(
                        {sub['AvailabilityZone']: sub['SubnetId']})

    except Exception as e:
        log.error(e)
        return None

    subnets=[]

    for subnet_mapping in az_subnet_mapping:
        for key,value in subnet_mapping.items():
            subnets.append(value)

    return(subnets)


def get_default_route_table(returned_vpc,cidr):
    default_route_table = ''

    try:
        describe_route_tables = EC2_CLIENT.describe_route_tables(
            Filters=[
                {
                    'Name':'vpc-id',
                    'Values': [returned_vpc]
                },
                {
                    'Name': 'association.main',
                    'Values': ['true']

                }
            ]
        )
        default_route_table = describe_route_tables['RouteTables'][0]['RouteTableId']

        describe_routes = EC2_CLIENT.describe_route_tables(
            RouteTableIds=[
                default_route_table,
            ],
        )
        describe_routes = describe_routes['RouteTables']

        for route in describe_routes[0]['Routes']:
            if route['DestinationCidrBlock'] == cidr:

                delete_existing_route = EC2_CLIENT.delete_route(
                    DestinationCidrBlock=cidr,
                    RouteTableId=default_route_table
                )

    except Exception as e:
        log.error(e)
        return None

    return default_route_table

def create_vpc_route_to_tgw(vpc_metadata, tgw_id, cidr):
    response_data = {}

    for entry in vpc_metadata:
        if entry['Subnet']:

            try:
                describe_routes = EC2_CLIENT.describe_route_tables(
                    RouteTableIds=[entry['Route_Table']],
                )
                describe_routes = describe_routes['RouteTables']

                for route in describe_routes[0]['Routes']:
                    if route['DestinationCidrBlock'] == cidr:

                        delete_existing_route = EC2_CLIENT.delete_route(
                            DestinationCidrBlock=cidr,
                            RouteTableId=entry['Route_Table']
                        )

                create_route = EC2_CLIENT.create_route(
                    RouteTableId=entry['Route_Table'],
                    DestinationCidrBlock=cidr,
                    TransitGatewayId=tgw_id
                )
                print('CREATED ROUTE to ' + cidr + ' for ' + entry['Route_Table'] +
                         ' with a destination of ' + tgw_id)

            except Exception as e:
                print('error in spoke attachment with: ' + entry['Subnet'])
                log.error(e)
                return None

def create_service_link_role():
    service_role_exists = False

    list_roles = IAM_CLIENT.list_roles(
    )

    for role in list_roles['Roles']:
        if role['RoleName'] == 'AWSServiceRoleForVPCTransitGateway':
            service_role_exists = True


    if not service_role_exists:
        create_role = IAM_CLIENT.create_service_linked_role(
            AWSServiceName='transitgateway.amazonaws.com',
            )
        print(create_role)

    return()


def setup_logging():
    """Setup Logging."""
    global log
    log = logging.getLogger()
    log_levels = {'INFO': 20, 'WARNING': 30, 'ERROR': 40}

    if 'logging_level' in os.environ:
        log_level = os.environ['logging_level'].upper()
        if log_level in log_levels:
            log.setLevel(log_levels[log_level])
        else:
            log.setLevel(log_levels['ERROR'])
            log.error("The logging_level environment variable is not set \
                      to INFO, WARNING, or ERROR. \
                      The log level is set to ERROR")
    else:
        log.setLevel(log_levels['ERROR'])
        log.warning('The logging_level environment variable is not set.')
        log.warning('Setting the log level to ERROR')
    log.info('Logging setup complete - set to log level '
             + str(log.getEffectiveLevel()))


def send(event, context, responseStatus, responseData, physicalResourceId=None, noEcho=False, reason=None):
    responseUrl = event['ResponseURL']

    print(responseUrl)

    responseBody = {
        'Status' : responseStatus,
        'Reason' : reason or "See the details in CloudWatch Log Stream: {}".format(context.log_stream_name),
        'PhysicalResourceId' : physicalResourceId or context.log_stream_name,
        'StackId' : event['StackId'],
        'RequestId' : event['RequestId'],
        'LogicalResourceId' : event['LogicalResourceId'],
        'NoEcho' : noEcho,
        'Data' : responseData
    }

    json_responseBody = json.dumps(responseBody)

    print("Response body:")
    print(json_responseBody)

    headers = {
        'content-type' : '',
        'content-length' : str(len(json_responseBody))
    }

    try:
        response = http.request('PUT', responseUrl, headers=headers, body=json_responseBody)
        print("Status code:", response.status)


    except Exception as e:

        print("send(..) failed executing http.request(..):", e)