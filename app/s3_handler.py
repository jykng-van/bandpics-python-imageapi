import boto3
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import piexif
import io
import asyncio
import re
import mimetypes
from concurrent.futures import ThreadPoolExecutor


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

    def delete_file(self, key):
        try:
            s3_task = self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return s3_task
        except ClientError as e:
            return {'error': str(e)}

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

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda:self.s3_client.copy_object(
                Bucket=self.bucket_name,
                CopySource=f"{self.bucket_name}/{old_key}",
                Key=new_key
            ))
            await loop.run_in_executor(None, lambda:self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=old_key
            ))

            return {'old_key':old_key, 'new_key':new_key}
        except ClientError as e:
            return {'error': str(e)}

    async def presign_file(self, group, filename):
        loop = asyncio.get_event_loop()
        try:
            key = f"original/{group}/{filename}"

            presigned_url = await loop.run_in_executor(None, lambda: self.s3_client.generate_presigned_url(
                'put_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=3600
            ))

            return {'presigned_url': presigned_url}

        except ClientError as e:
            return {'error': str(e)}

    async def upload_image(self, group, filename, bytes):
        loop = asyncio.get_event_loop()
        tasks = []


        proposed_key = f"thumb/{group}/{filename}"
        if await self.file_exists(proposed_key): #prevent overwrite
            new_key = await self.number_matching_files(new_key)
            filename = os.path.basename(new_key)


        with ThreadPoolExecutor() as pool:
            max_size = self.fullsize_side #max size for longest side

            display_image = Image.open(io.BytesIO(bytes))
            display_exif = self.remove_gps(display_image) #remove gps data

            #Thumbnail image
            thumbnail_image = display_image.copy()
            thumbnail_image.thumbnail((self.thumbnail_side, self.thumbnail_side), Image.LANCZOS) # create thumbnail
            thumbnail_stream = io.BytesIO()
            thumbnail_image.save(thumbnail_stream, format='JPEG', exif=display_exif)
            thumbnail_stream.seek(0)

            thumbnail_path = f"thumb/{group}"
            tasks.append(loop.run_in_executor(pool, self.upload_file, thumbnail_stream,  thumbnail_path, filename)) # upload thumbnail image

            #Fullsize image
            fullsize_image = display_image.copy()
            size = display_image.size
            print(f"Image size: {size}")

            fullsize_image.thumbnail((max_size, max_size), Image.LANCZOS) # create thumbnail

            fullsize_stream = io.BytesIO() # prepare stream for display image
            fullsize_image.save(fullsize_stream, format='JPEG', exif=display_exif)
            fullsize_stream.seek(0)

            fullsize_path = f"fullsize/{group}"
            tasks.append(loop.run_in_executor(pool, self.upload_file, fullsize_stream, fullsize_path, filename)) # upload fullsize image

            """ original_path = f"{group}/original"
            tasks.append(loop.run_in_executor(pool, self.upload_file, io.BytesIO(bytes), original_path, filename)) #upload original image """

        await asyncio.gather(*tasks)
        return {
            'filename':filename,
            'files':[
                #f"{original_path}/{filename}",
                f"{fullsize_path}/{filename}",
                f"{thumbnail_path}/{filename}",
            ]
        }

    def remove_gps(self, image):
        exif_data = piexif.load(image.info.get('exif',''))
        del exif_data['GPS']
        return piexif.dump(exif_data)

    async def delete_image(self, group, filename):
        loop = asyncio.get_event_loop()
        tasks = []
        folders = ['original', 'fullsize', 'thumb']
        files = []
        with ThreadPoolExecutor() as pool:
            for folder in folders:
                key = f"{folder}/{group}/{filename}"
                tasks.append(loop.run_in_executor(pool, self.delete_file, key))
                files.append(key)
        await asyncio.gather(*tasks)
        return {
            'group':group,
            'filename':filename,
            'files':files
        }

    async def move_image(self, old_group, new_group, filename):
        tasks = []
        folders = ['original', 'fullsize', 'thumb']

        for folder in folders:
            #tasks.append(loop.run_in_executor(pool, self.move_file, filename, f"{old_group}/{folder}", f"{new_group}/{folder}"))
            await self.move_file(filename, f"{folder}/{old_group}", f"{folder}/{new_group}")
        results = await asyncio.gather(*tasks)

        return results

if __name__ == '__main__':
    s3_handler = S3Handler()