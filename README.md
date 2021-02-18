
# ec2-auto-ami-manager

> AWS Lambda function written in Python to manage EC2 images

## Description

The Lambda function "*ec2-auto-ami-manager*" provides automatic EC2 image (AMI) creation, copy and deletion as backup strategy.

## Features

 - Automatic image creation configured by EC2 tags
 - Automatic image deletion on expiration date
 - Automatic cross region image copy
 - All or pre-defined aws region verification
 - Can run locally outside AWS Lambda

## Lambda Creation

Follow these steps to get your lambda function running.

### IAM Role

Add this IAM role. It will be attached to your lambda function.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

You can add via command line

```
aws iam create-role --role-name lambda-ec2-auto-ami-manager --path /service-role/ --description "Automatic EC2 image creation and deletion" --assume-role-policy-document https://raw.githubusercontent.com/rodrigoluissilva/ec2-auto-ami-manager/master/lambda-role.json
```

### IAM Policy

Now you have to attach this policy to allow a few actions to be performed.

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogStream",
                "logs:CreateLogGroup",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:log-group:/aws/lambda/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeImages",
                "ec2:DeregisterImage",
                "ec2:DescribeInstances",
                "ec2:CreateTags",
                "ec2:CreateSnapshot",
                "ec2:CreateImage",
                "ec2:CopyImage",
                "ec2:DeleteSnapshot",
                "ec2:DescribeRegions",
                "ec2:DescribeSnapshots"
            ],
            "Resource": "*"
        }
    ]
}
```

This can be done via command line

```
aws iam put-role-policy --role-name lambda-ec2-auto-ami-manager --policy-name ec2-image-manager --policy-document https://raw.githubusercontent.com/rodrigoluissilva/ec2-auto-ami-manager/master/lambda-policy.json
```

### Lambda Function

#### Console

Add a new Lambda function using these options.

**Name**: ec2-auto-ami-manager
**Runtime**: Python 3.6
**Existing Role**: service-role/lambda-ec2-auto-ami-manager

![Lambda Create Function Sample Screen](https://image.prntscr.com/image/JFGuThBuQ_2UM7PEBMYL3g.png)

Change the **timeout to 5 minutes** and add some useful description.

![Lambda Function Basic Settings Sample Screen](https://image.prntscr.com/image/60yfDUxpSy2X-MPenArlLw.png)

Paste the code from the file *ec2-auto-ami-manager.py* in the Lambda Function Code area.

You can set a test event using the "**Scheduled Event**" template.

#### Command Line

Download the file *ec2-auto-ami-manager.py*.
Rename it to *lambda_function.py*.
Compress it as a *zip file*.

Get the IAM Role ARN using this command.

```
aws iam get-role --role-name lambda-ec2-auto-ami-manager
```

Replace the ARN by the one from the previous command.

```
aws lambda create-function --region us-east-1 --function-name ec2-auto-ami-manager --description "Automatic EC2 image (AMI) creation and deletion as backup strategy" --zip-file fileb://lambda_function.zip --handler lambda_function.lambda_handler --runtime python3.6 --timeout 300 --role arn:aws:iam::XXXXXXXXXXXX:role/lambda-ec2-auto-ami-manager
```

## Schedule

This lambda function is triggered by one CloudWatch Event Rule.
Run this command to set it to run at 3 am everyday.

```
aws events put-rule --name ec2-auto-ami-manager --schedule-expression "cron(0 3 * * ? *)" --description "Trigger the ec2-auto-ami-manager function"
```

Add permission to CloudWatch invoke the Lambda Function.
Use the ARN from the previous command.

```
aws lambda add-permission --function-name ec2-auto-ami-manager --statement-id ec2-auto-ami-manager --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn arn:aws:events:us-east-1:XXXXXXXXXXXX:rule/ec2-auto-ami-manager
```

Get the Lambda Function ARN with this command.

```
aws lambda get-function-configuration --function-name ec2-auto-ami-manager
```

Replace this ARN by the one from the previous command.

```
aws events put-targets --rule ec2-auto-ami-manager --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:XXXXXXXXXXXX:function:ec2-auto-ami-manager"
```

## EC2 Configuration

The default tag is "*scheduler:ec2-auto-ami-creation*"

To enable the backup, add this tag and the value following the specific pattern as described bellow.

**Key**: scheduler:ec2-auto-ami-creation

**Value**: Enable=Yes;Type=Weekly;When=Tuesday;Retention=2;CopyTags=Yes;CopyTo=us-west-1

The minimum setting for a daily image creation is

**Key**: scheduler:ec2-auto-ami-creation

**Value**: Enable=Yes

### Parameters details

| Parameter | Description |Values|
|--|--|--|
| **Enable** |Enable or Disable image auto creation. <br> You need at least this parameter to enable the daily image creation.| **Yes** – Enable<br>**No** – Disable (**default**) |
| **Type** | How often to take an image. | **Always** – Will take one image on every execution<br>**Daily** – One image per day (**default**)<br>**Weekly** – One image on the weekday defined on the parameter "When"<br>**Monthly** – One image on the day defined on the parameter "When" |
|**When**|When this image will be taken<br>Could be one or more values.<br><br>When=Tuesday<br>When=Sunday, Thursday<br>When=Mon, Sat<br>When=25<br>When=1, 15<br>When=1, 10, 20|**Always and Daily**<br>This option is not used<br><br>**Weekly**<br>Sun, Mon, ..., Sat<br>Sunday, Monday, ..., Saturday<br><br>**Monthly**<br>1, 2, 3, ..., 31|
|**Retention**|The number of days to keep the image.|1, 2, 3, 4, 5, ...<br> (**default**: 2)|
|**CopyTags**|Copy EC2 tags to the image.|**Yes** – Copy all EC2 tags<br>**No** – Don’t copy EC2 tags (**default**)|
|**CopyTo**|Make a copy of this image to a different region.<br>Could be one or more values.<br><br>CopyTo=us-east-2<br>CopyTo=us-east-2, us-west-1|ap-south-1, eu-west-3, eu-west-2, eu-west-1, ap-northeast-2, ap-northeast-1, sa-east-1, ca-central-1, ap-southeast-1, ap-southeast-2, eu-central-1, us-east-1, us-east-2, us-west-1, us-west-2<br><br>**Default**: None|
|**Reboot**|Attempts to shutdown and reboot the instance before creating the image.|**Yes** – Reboot<br>**No** – Don’t reboot (**default**)|

## Lambda Environment Variables

You can set a few environment variables to control how the Lambda Function will behave.

Key|Description|Value
-|-|-
**custom_aws_regions**|A list of AWS Regions to be used during the execution time.<br>Could be one or more regions.<br><br>custom_aws_regions=us-east-1, us-east-2, us-west-1|Any valid AWS region.
**custom_tag**|Define the tag name to be used.|Any valid tag name.
**default_retention_days**|The default retention period in days.|Any valid number of days.