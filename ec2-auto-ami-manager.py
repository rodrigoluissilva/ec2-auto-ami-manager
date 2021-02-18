#!/usr/bin/env python

""" AWS Lambda Function to manage EC2 images

This Lambda Function provides automatic EC2 image (AMI)
creation, copy and deletion as backup strategy.

Features

 - Automatic image creation configured by EC2 tags
 - Automatic image deletion on expiration date
 - Automatic cross region image copy
 - All or pre-defined aws region verification
 - Can run locally outside AWS Lambda

-------

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

__author__ = "Rodrigo Luis Silva"
__url__ = "https://github.com/rodrigoluissilva/ec2-auto-ami-manager"
__deprecated__ = False
__license__ = "GPLv3"
__status__ = "Production"
__version__ = "1.0.0"

import os
import uuid
import boto3
import locale
import datetime
import botocore
import logging

try:
    locale.setlocale(locale.LC_TIME, 'en_US.utf8')
except locale.Error:
    pass


class AMIBackup(object):

    def __init__(self):
        self.custom_tag = os.environ.get('custom_tag', 'scheduler:ec2-auto-ami-creation')
        self.default_retention_days = int(os.environ.get('default_retention_days', 2))
        custom_aws_regions = os.environ.get('custom_aws_regions', None)

        self.request_id = uuid.uuid4()

        """ Logging setup """
        logging.basicConfig(format='%(asctime)-15s [%(name)s] [%(levelname)s] '
                                   '[%(function_name)s] [%(request_id)s] '
                                   '[%(aws_region)s] %(message)s')
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        """ AWS Region lookup """
        ec2client = boto3.client('ec2')
        if custom_aws_regions is not None:
            self.aws_regions = [region.strip().lower()
                                for region in custom_aws_regions.split(',')]
        else:
            self.aws_regions = [region['RegionName']
                                for region in ec2client.describe_regions()['Regions']]

    def create_images(self, region):
        ec2 = boto3.resource('ec2', region_name=region)
        log_extra = {'request_id': self.request_id,
                     'aws_region': region,
                     'function_name': 'create_images'}

        self.logger.debug('Start checking...', extra=log_extra)

        instances = ec2.instances.filter(Filters=
                                         [{'Name': 'tag-key',
                                           'Values': [self.custom_tag]}]
                                         )

        for instance in instances:

            today_date = datetime.date.today()
            today_datetime = datetime.datetime.now().strftime('%Y-%M-%d_%H-%M-%S')
            today_weekday = datetime.date.strftime(today_date, '%a').lower()
            today_day = int(datetime.date.strftime(today_date, '%d'))

            instance_name = instance.instance_id
            backup_this_instance = False
            parse_error = False

            self.logger.debug('Variables for ({}): today_date={}, today_datetime={}, '
                              'today_weekday={}, today_day={}, '
                              'instance_name={}'.format(instance.instance_id,
                                                        today_date,
                                                        today_datetime,
                                                        today_weekday,
                                                        today_day,
                                                        instance_name,
                                                        backup_this_instance,
                                                        parse_error),
                              extra=log_extra)

            for tag in instance.tags:
                if tag['Key'] == 'Name':
                    instance_name = tag['Value']
                elif tag['Key'] == self.custom_tag:
                    try:
                        self.logger.debug('Values for tag ({}) in '
                                          '({}): ({})'.format(self.custom_tag,
                                                              instance.instance_id,
                                                              tag['Value']),
                                          extra=log_extra)
                        config = {k.lower().strip(): v.lower().strip()
                                  for k, v in [option.split('=')
                                               for option in tag['Value'].split(';')]}
                    except ValueError:
                        parse_error = tag['Value']
                        config = {'enable': 'no'}

                    backup_copy_to = config.get('copyto')
                    backup_retention = int(config.get('retention')) \
                        if config.get('retention', '').strip().isdigit() \
                        else self.default_retention_days
                    backup_enable = True \
                        if config.get('enable') in ('yes', 'true') \
                        else False
                    backup_type = config.get('type') \
                        if config.get('type') in ('always', 'daily', 'weekly', 'monthly') \
                        else None
                    backup_copy_tags = True \
                        if config.get('copytags') in ('yes', 'true') \
                        else False
                    backup_no_reboot = False \
                        if config.get('reboot') in ('yes', 'true') \
                        else True

            self.logger.debug('Variables for ({}): backup_enable={}, backup_type={}, '
                              'backup_copy_tags={}, backup_copy_to={}, '
                              'backup_retention={}, backup_no_reboot={}'.format(instance.instance_id,
                                                                                backup_enable,
                                                                                backup_type,
                                                                                backup_copy_tags,
                                                                                backup_copy_to,
                                                                                backup_retention,
                                                                                backup_no_reboot),
                              extra=log_extra)

            if backup_enable:

                backup_this_instance = True

                if backup_type == 'always':
                    name_qualifier = str(today_datetime)
                else:
                    name_qualifier = str(today_date)

                if backup_type == 'weekly' and \
                        today_weekday not in [wd.strip().lower()[:3]
                                              for wd in config.get('when').split(',')]:
                    backup_this_instance = False

                if backup_type == 'monthly' and \
                        today_day not in [int(d)
                                          for d in config.get('when').split(',')
                                          if d.strip().isdigit() and int(d) in range(1, 32)]:
                    backup_this_instance = False

            if backup_this_instance:
                expire_date = str(today_date + datetime.timedelta(days=backup_retention))
                image_name = '{} - {}'.format(instance.instance_id, name_qualifier)
                image_description = '{} - ({}) - {}'.format(instance.instance_id,
                                                            instance_name,
                                                            today_date)
                try:
                    instance_image = instance.create_image(Description=image_description,
                                                           Name=image_name,
                                                           NoReboot=backup_no_reboot)
                except botocore.exceptions.ClientError as e:
                    if e.response['Error']['Code'] == 'InvalidAMIName.Duplicate':
                        self.logger.info('Skipping instance ({}) '
                                         '({}) image already exist'.format(instance.instance_id,
                                                                           instance_name),
                                         extra=log_extra)
                    else:
                        self.logger.error('Error trying to create '
                                          'image for {}: {}'.format(instance.instance_id,
                                                                    e.response['Error']['Message']),
                                          extra=log_extra)
                    continue

                if backup_copy_tags:
                    instance_image.create_tags(Tags=instance.tags)
                instance_image.create_tags(Tags=
                                           [{'Key': self.custom_tag,
                                             'Value': expire_date + ';' + str(backup_copy_to)}]
                                           )
                self.logger.warning('Creating image ({}) for ({}) '
                                    'to be deleted on ({})'.format(instance_image.image_id,
                                                                   instance_name,
                                                                   expire_date),
                                    extra=log_extra)
            else:
                if backup_enable is False:
                    if parse_error:
                        self.logger.error('Error in instance ({}) ({}) '
                                          'parsing tag value [{}]'.format(instance.instance_id,
                                                                          instance_name,
                                                                          parse_error),
                                          extra=log_extra)
                    else:
                        self.logger.info('Backup disabled for instance '
                                         '({}) ({})'.format(instance.instance_id,
                                                            instance_name),
                                         extra=log_extra)
                else:
                    self.logger.info('Skipping instance ({}) ({}): '
                                     'Backup is {} on {}'.format(instance.instance_id,
                                                                 instance_name,
                                                                 backup_type.title(),
                                                                 config.get('when').title()),
                                     extra=log_extra)

    def copy_images(self, region):
        ec2 = boto3.resource('ec2', region_name=region)
        log_extra = {'request_id': self.request_id,
                     'aws_region': region,
                     'function_name': 'copy_images'}

        self.logger.debug('Start checking...', extra=log_extra)

        images = ec2.images.filter(
                Filters=[{'Name':   'tag-key',
                          'Values': [self.custom_tag]},
                         {'Name': 'state',
                          'Values': ['available']}
                         ]
                )
        for image in images:
            self.logger.debug('Checking image ({})'.format(image.image_id), extra=log_extra)
            for tag in image.tags:
                if tag['Key'] == self.custom_tag:
                    expire_date, copy_targets = tag['Value'].split(';')
                    self.logger.debug('Image ({}): expire_date={}, '
                                      'copy_targets={}'.format(image.image_id,
                                                               expire_date,
                                                               copy_targets),
                                      extra=log_extra)
                    for copy_target in [target.strip() for target in copy_targets.split(',')]:
                        if copy_target in self.aws_regions:
                            try:
                                ec2_target = boto3.resource('ec2', region_name=copy_target)
                                ec2cli_target = boto3.client('ec2', region_name=copy_target)
                                description = '[Copied {} from {}] {}'.format(image.image_id,
                                                                              region,
                                                                              image.description)
                                image_copy = ec2cli_target.copy_image(Description=description,
                                                                      Name=image.name,
                                                                      SourceImageId=image.image_id,
                                                                      SourceRegion=region)['ImageId']
                                image_copy = ec2_target.Image(image_copy)
                                image_copy.create_tags(Tags=image.tags)
                                new_tag = [{'Key': self.custom_tag, 'Value': expire_date + ';None'}]
                                image_copy.create_tags(Tags=new_tag)
                                image.create_tags(Tags=new_tag)
                                self.logger.warning('Copying image ({}) to ({}) '
                                                    'with id ({})'.format(image.image_id,
                                                                          copy_target,
                                                                          image_copy.image_id),
                                                    extra=log_extra)
                            except Exception as e:
                                self.logger.error('Error copying image ({}) '
                                                  'to ({}): {}'.format(image.image_id,
                                                                       copy_target,
                                                                       e.response['Error']['Message']),
                                                  extra=log_extra)

    def remove_images(self, region):
        ec2 = boto3.resource('ec2', region_name=region)
        log_extra = {'request_id': self.request_id,
                     'aws_region': region,
                     'function_name': 'remove_images'}

        self.logger.debug('Start checking...', extra=log_extra)

        images = ec2.images.filter(
                Filters=[{'Name':   'tag-key',
                          'Values': [self.custom_tag]},
                         {'Name':   'state',
                          'Values': ['available']}
                         ]
                )
        for image in images:
            self.logger.debug('Checking image ({})'.format(image.image_id), extra=log_extra)
            for tag in image.tags:
                if tag['Key'] == self.custom_tag:
                    expire_date = tag['Value'].split(';')[0]
                    self.logger.debug('Image ({}): expire_date={}'.format(image.image_id,
                                                                          expire_date),
                                      extra=log_extra)
                    if datetime.datetime.strptime(expire_date, '%Y-%m-%d') \
                            <= datetime.datetime.combine(datetime.date.today(), datetime.time.min):
                        snapshots = []
                        for snapshot in image.block_device_mappings:
                            if 'Ebs' in snapshot:
                                snapshots.append(snapshot['Ebs']['SnapshotId'])
                        self.logger.warning('Removing image ({}) with snapshots '
                                            '({}) expired on {}'.format(image.image_id,
                                                                        '|'.join(snapshots),
                                                                        expire_date),
                                            extra=log_extra)
                        try:
                            image.deregister()
                            for snapshot in ec2.snapshots.filter(SnapshotIds=snapshots):
                                try:
                                    snapshot.delete()
                                except Exception as e:
                                    self.logger.error('Error to delete snapshot '
                                                      '({}): {}'.format(snapshot.snapshot_id,
                                                                        e.response['Error']['Message']),
                                                      extra=log_extra)
                        except Exception as e:
                            self.logger.error('Error to deregister image '
                                              '({}): {}'.format(image.image_id,
                                                                e.response['Error']['Message']),
                                              extra=log_extra)
                    else:
                        self.logger.info('Keeping image ({}) until ({})'.format(image.image_id,
                                                                                expire_date),
                                         extra=log_extra)


def lambda_handler(event=None, context=None):
    ami_backup = AMIBackup()
    if context is not None:
        ami_backup.request_id = context.aws_request_id

    for region in ami_backup.aws_regions:
        ami_backup.create_images(region)
        ami_backup.remove_images(region)
        ami_backup.copy_images(region)


if __name__ == '__main__':
    lambda_handler()
