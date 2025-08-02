import boto3
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

import io
import asyncio
import re
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from app.image_data_handler import ImageDataHandler


class S3Handler:
    fullsize_side = 2880
    thumbnail_side = 300

    # Initialize the S3 client, assuming a role to access S3
    def __init__(self):
        load_dotenv()
        self.aws_region = os.getenv('AWS_DEFAULT_REGION')
        self.assume_role_arn = os.getenv('S3_ROLE_ARN')

        sts_client = boto3.client('sts', region_name=self.aws_region)
        response = sts_client.assume_role(
            RoleArn=self.assume_role_arn,
            RoleSessionName='bandpics-s3-session'
        )
        temp_credentials = response["Credentials"]

        self.s3_client = boto3.client('s3',
            region_name=self.aws_region,
            aws_secret_access_key=temp_credentials['SecretAccessKey'],
            aws_access_key_id=temp_credentials['AccessKeyId'],
            aws_session_token=temp_credentials['SessionToken'])
        self.bucket_name = os.getenv('S3_BUCKET_NAME')

    # Direct upload to S3, deprecated since lambda's limits favour presigned URLs
    def upload_file(self, file_bytes, prefix, filename):
        try:
            print(f"Bucket: {self.bucket_name}")
            mime, encoding = mimetypes.guess_type(filename)
            s3_task = self.s3_client.put_object(
                Body=file_bytes,
                Bucket=self.bucket_name,
                Key=f"{prefix}/{filename}",
                ContentType=mime
            )
            print(f"File {prefix}/{filename} (Etag: {s3_task['ETag']}) uploaded")
            return s3_task
        except ClientError as e:
            return {'error': str(e)}

    # Delete a file from S3
    def delete_file(self, key):
        print('deleting', key)
        try:
            s3_task = self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return s3_task
        except ClientError as e:
            return {'error': str(e)}
    # Check if a file exists in S3
    async def file_exists(self, key):
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.s3_client.head_object(Bucket=self.bucket_name, Key=key))
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                print(str(e))
            return False
    # List files in S3 with a prefix
    async def list_files(self, prefix):
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix))
            contents = response.get('Contents', [])
            contents = [item['Key'] for item in contents]
            return contents
        except ClientError as e:
            print(str(e))
            return None
    # Generate a new filename by appending a number if it exists, ex: "image.jpg" becomes "image-1.jpg"
    async def number_matching_files(self, key):
        find = re.sub(r"\.[^.]*$", "", key) # Remove the file extension
        ext = re.search(r"\.[^.]*$", key).group(0) # Get the file extension
        print(find, ext)

        matching_files = await self.list_files(find)

        if len(matching_files) > 0:
            max_number = 0
            for filename in matching_files:
                number = re.search(r"-(\d+)\.[^.]*$", filename) # Find the number
                if number is not None:
                    num = int(number.group(1))
                    max_number = max(max_number, num)

            suffix = max_number + 1 # suffix is 1 greater than the max
            return f"{find}-{suffix}{ext}"
        else:
            return key
    # Check if a file with a prefix/folder exists and rename if if it does
    async def check_and_rename_file(self, prefix, filename):
        key = f"{prefix}/{filename}"
        if (await self.file_exists(key)): #prevent overwrite
            key = await self.number_matching_files(key) # append number to filename if it exists
        return key

    # you can't move an object you must copy the object to a new name and then delete the old one
    async def move_file(self, filename, old_prefix, new_prefix):
        try:
            old_key = f"{old_prefix}/{filename}"
            new_key = await self.check_and_rename_file(new_prefix, filename)
            print('move file', old_key, new_key)

            loop = asyncio.get_event_loop()
            # Copy to new location
            await loop.run_in_executor(None, lambda:self.s3_client.copy_object(
                Bucket=self.bucket_name,
                CopySource=f"{self.bucket_name}/{old_key}",
                Key=new_key
            ))
            # Delete from old location
            await loop.run_in_executor(None, lambda:self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=old_key
            ))

            return {'old_key':old_key, 'new_key':new_key}
        except ClientError as e:
            return {'error': str(e)}
    # Generate a presigned URL for uploading to S3
    async def presign_file(self, filename):
        loop = asyncio.get_event_loop()
        try:
            key = f"original/{filename}"
            mimetype = mimetypes.guess_type(filename)[0]

            presigned_url = await loop.run_in_executor(None, lambda: self.s3_client.generate_presigned_url(
                ClientMethod='put_object', # the method in S3, essential that it's ClientMethod
                Params={'Bucket': self.bucket_name, 'Key': key, 'ContentType':mimetype},
                ExpiresIn=1800, # expiration time in seconds
                HttpMethod='PUT',
            ))

            return {'presigned_url': presigned_url, 'type': mimetype}

        except ClientError as e:
            return {'error': str(e)}
    # Process an image that was uploaded to S3, this will create a thumbnail and image sized for display
    # It removes GPS data from the new images
    async def process_image(self, group, filename):
        loop = asyncio.get_event_loop()
        tasks = []

        if await self.file_exists(f"original/{group}/{filename}"): # check if file exists
            print("Yes file exists")

            with ThreadPoolExecutor() as pool:
                max_size = self.fullsize_side #max size for longest side

                # get image bytes from S3
                image_stream = io.BytesIO() #stream to hold the image bytes
                print(self.bucket_name, f"orginal/{group}/{filename}")
                # download from s3 to image_stream
                await loop.run_in_executor(pool, lambda: self.s3_client.download_fileobj(self.bucket_name, f"original/{group}/{filename}", image_stream))
                display_image = Image.open(image_stream) # open the image from stream
                print(display_image)
                image_handler = ImageDataHandler(display_image) # create ImageDataHandler

                date_and_coords = image_handler.get_date_and_coords() #get dat and coordinates from image
                print('Date and coords:', date_and_coords)

                display_exif = image_handler.remove_gps(display_image) #remove gps data

                #Thumbnail image
                thumbnail_image = display_image.copy() #create a copy for thumbnail
                thumbnail_image.thumbnail((self.thumbnail_side, self.thumbnail_side), Image.LANCZOS) # resize to thumbnail size
                thumbnail_stream = io.BytesIO() # prepare stream from thumb
                thumbnail_image.save(thumbnail_stream, format='JPEG', exif=display_exif) #save thumb
                thumbnail_stream.seek(0) # seek beginning so it can be read for the upload

                thumbnail_path = f"thumb/{group}" # path for thumb
                tasks.append(loop.run_in_executor(pool, self.upload_file, thumbnail_stream,  thumbnail_path, filename)) # upload thumbnail image

                #Fullsize image
                fullsize_image = display_image.copy() # copy for fullsize
                size = display_image.size # get size of original, we aren't using this for resizing though
                print(f"Image size: {size}")

                fullsize_image.thumbnail((max_size, max_size), Image.LANCZOS) # resize to max size

                fullsize_stream = io.BytesIO() # prepare stream for display image
                fullsize_image.save(fullsize_stream, format='JPEG', exif=display_exif) # save fullsize image to stream
                fullsize_stream.seek(0) # seek beginning so it can be read for the upload

                fullsize_path = f"fullsize/{group}" # set path for fullsize
                tasks.append(loop.run_in_executor(pool, self.upload_file, fullsize_stream, fullsize_path, filename)) # upload fullsize image

        await asyncio.gather(*tasks)
        return {
            'filename':filename,
            'data': date_and_coords,
            'files':[
                f"{fullsize_path}/{filename}",
                f"{thumbnail_path}/{filename}",
            ]
        }

    # Delete an image and all its different sizes from S3
    async def delete_image(self, group, filename):
        print('s3_handler delete_image', group, filename)
        loop = asyncio.get_event_loop()
        tasks = [] # tasks pool
        folders = ['original', 'fullsize', 'thumb'] # the folders to delete from
        files = [] # list of files to delete
        with ThreadPoolExecutor() as pool:
            for folder in folders:
                key = f"{folder}/{group}/{filename}" # the patterns of the paths
                tasks.append(loop.run_in_executor(pool, self.delete_file, key)) # delete the file
                files.append(key) # add to files to delete
        await asyncio.gather(*tasks)
        return {
            'group':group,
            'filename':filename,
            'files':files
        }

    # Move an image and all its different sizes from one group to another
    async def move_image(self, old_group, new_group, filename):
        tasks = []
        folders = ['original', 'fullsize', 'thumb'] # the subfolders to move from

        for folder in folders:
            await self.move_file(filename, f"{folder}/{old_group}", f"{folder}/{new_group}") # move the file
        results = await asyncio.gather(*tasks)

        return results

if __name__ == '__main__':
    s3_handler = S3Handler()