# chkp-gwlb
AWS VPC architecture to support EWNS traffic inspection w/ GWLB &amp; Check Point CGNS with ALB for ingress

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
