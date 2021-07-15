# CloudGuard Network Security Architectures for GWLB
AWS VPC architecture to support  traffic inspection w/ Check Point CGNS via GWLB Security VPC with ALB for ingress

## What does it to?

This is an extension of Check Point AWS Cloud Formation templates for deployment of GWLB architectures.  This template creates a Securityu VPC + Internet VPC and optionally attaches them to a TGW for a centralized Security VPC with inspection by CGNS.

## Requirements
- ability to deploy cloud formation templates
- optional - ability to create and run Lambda Functions if you want to create TGW attachments

## Instructions for using this CFT:
1. Copy 3 YAML & 1 ZIP from this repo into an S3 bucket in your AWS account
2. Create a CloudFormation Stack using the S3 URL from either
    - tgw-gwlb-master.yaml to create new Security & Internet VPCs
    - tgw-gwlb.yaml to re-use existing Security & Internet VPCs
3. Enter paramaters as needed:
    - StackName: Give the Stack a Name as reference
    - S3Bucket: this is the S3 bucket where yaml and zip files were stored in step 1
    - LambdaS3Key: the filename for lambda.zip file (if it was changed or stored in a folder)
    - TGW ID: Enter the ID of your TGW if you want to Attach the Security & Internet VPCs to your TGW and add spoke routes for RFC 1918 subnets.  Leave blank to skip this action
    - General Settings:
        - Management Server: Enter the Management server name to be used by CME for autoprovisioning of CGNS gateways
        - Configuration Template: Enter a CME configuration template name for this deployment.  Must be unique within SMS/MDS if there are multiple CME templates in use 
        - Email address: enter a notification address to get notifications when the AutoScalingGroup deploys or terminates a CGNS instance
    - Gateway Load Balancer Configuration:
        - Gateway Load Balancer Name: Name assigned to AWS GWLB
        - Target Group Name: Name assigned to AWS Target group used by GWLB
4. CFT executes the followign
    - creates GWLB infrastgructure and CGNS ASG
    - creates a Lambda Function to create TGW attachments and RT creation/association for Security & Internet VPC
    - adds routes for 10.0.0.0/8 --> TGW to Security & Internet VPCs 
5. Optional modifications in **tgw-gwlb.yaml**
    - Modify routes as needed for SMS/MDS management in the Security Subnet Route tables for each AZ
   ```
        SecSubnet<1-4>TGW10Route
   ```
    - Add RFC1918 or other internal Network IP Address to Inet VPC
   ```
        InetVPC10SpokeRoute
    ```
##Script currently completes:
- TGW Attachment for Security VPC & Inet VPC
- TGW Route table creation for security VPC Egress & Ingress RT
- Route Propagation of Inet VPC routes into TGW Egress RT
- Static route 0.0.0.0/0 --> Security VPC into TGW Ingress RT

##Future script capabilities: 
- Search for VPC's with a given tag to attach to TGW
    - For Each properly Tagged VPC
        - Create TGW attachment for the Tagged VPC
        - Associate TGW Ingress RT to the newly created Attachment
        - Create Route propagaton for Tagged VPC into TGW Egress RT
        - Add 0.0.0.0/0 --> TGW route to all Tagged VPC subnet RT
    
### Notes/caveats
- Spoke VPC associations work, but as we must wait up to 60 seconds for TGW associations and propagations to complete, the overall time of completing Security + Inet + Spoke VPC associations exceeds Lambda Max Run Time of 15 mins.  Need to break this down into smaller functions

## References:
- [Check Point CloudFormation Templates](https://supportcenter.checkpoint.com/supportcenter/portal?eventSubmit_doGoviewsolutiondetails=&solutionid=sk111013)
- [Automating AWS Transit Gateway attachments to a transit gateway in a central account](https://aws.amazon.com/blogs/networking-and-content-delivery/automating-aws-transit-gateway-attachments-to-a-transit-gateway-in-a-central-account/)
