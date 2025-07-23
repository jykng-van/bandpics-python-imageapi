import unittest
from unittest.mock import patch, MagicMock
import boto3
from moto import mock_aws
from app.s3_handler import S3Handler
from PIL import Image
import piexif
import io

class test_s3_handler(unittest.IsolatedAsyncioTestCase):
    region_name = 'us-east-1'
    bucket_name = 'test-bucket'

    def setUp(self):
        self.mock_aws = mock_aws()
        self.mock_aws.start()

        # you can use boto3.client("s3") if you prefer
        boto3.client('sts', region_name=self.region_name)
        s3 = boto3.client("s3", region_name=self.region_name)
        s3.create_bucket(Bucket=self.bucket_name)

        self.s3_handler = S3Handler()
        self.s3_handler.s3_client = s3
        self.s3_handler.bucket_name = self.bucket_name

    def tearDown(self):
        self.mock_aws.stop()

    def create_test_image(self, width=100, height=100, color='red', gps_data={}):
        image = Image.new('RGB', (width, height), color=color)
        stream = io.BytesIO()
        exif_dict = {"0th":{}, "Exif":{}, "GPS":gps_data, "1st":{}, "thumbnail":None}
        exif_bytes = piexif.dump(exif_dict)
        image.save(stream, format='JPEG', exif=exif_bytes)
        stream.seek(0)
        return stream

    # Test upload_file
    def test_upload_file(self):
        image_bytes = self.create_test_image()

        prefix = 'test'
        filename = 'test_image.jpg'
        result = self.s3_handler.upload_file(image_bytes, prefix, filename)
        print(result)

        assert result['ETag'] is not None, "ETag expected" #check if ETag is returned

        # verify the file was uploaded
        s3 = boto3.resource("s3")
        object = s3.Object(self.bucket_name, f"{prefix}/{filename}")
        actual = object.get()["Body"].read()

        assert actual == image_bytes.getvalue(), "Uploaded file content doesn't match"

    # Test delete_file
    def test_delete_file(self):
        image_bytes = self.create_test_image()
        key = 'test/test_image.jpg'

        s3 = boto3.resource("s3")
        s3.Object(self.bucket_name, key).put(Body=image_bytes)

        result = self.s3_handler.delete_file(key)
        print(result)
        assert result['ResponseMetadata']['HTTPStatusCode'] == 204, "Expected status code 204"

        # verify the file was deleted
        s3 = boto3.resource("s3")
        object = s3.Object(self.bucket_name, key)
        try:
            object.get()
            assert False, "Expected object to be deleted"
        except s3.meta.client.exceptions.NoSuchKey:
            assert True

    # Test file_exists
    async def test_file_exists(self):
        image_bytes = self.create_test_image()
        key = 'test/test_image.jpg'

        s3 = boto3.resource("s3")
        s3.Object(self.bucket_name, key).put(Body=image_bytes)

        exists = await self.s3_handler.file_exists(key)
        assert exists, "File should exist"

        not_exists = await self.s3_handler.file_exists('test/not_existing.jpg')
        assert not not_exists, "File should not exist"

    # Test list_files
    async def test_list_files(self):
        # Create two images
        image_bytes1 = self.create_test_image()
        key1 = 'test/test_image1.jpg'

        image_bytes2 = self.create_test_image(color='green')
        key2 = 'test/test_image2.jpg'

        s3 = boto3.resource("s3")
        s3.Object(self.bucket_name, key1).put(Body=image_bytes1)
        s3.Object(self.bucket_name, key2).put(Body=image_bytes2)

        files = await self.s3_handler.list_files('test/test_image')

        print(files)
        assert len(files) == 2, "Expected two files"
        assert key1 in files, "Expected first file to be listed"
        assert key2 in files, "Expected second file to be listed"

    # Test number_matching_files
    async def test_number_matching_files(self):
        # Create two images
        image_bytes1 = self.create_test_image()
        key1 = 'test/test_image.jpg'

        image_bytes2 = self.create_test_image(color='green')
        key2 = 'test/test_image-1.jpg'

        s3 = boto3.resource("s3")
        s3.Object(self.bucket_name, key1).put(Body=image_bytes1)
        s3.Object(self.bucket_name, key2).put(Body=image_bytes2)

        new_key = await self.s3_handler.number_matching_files(key1)
        print(new_key)
        assert new_key == 'test/test_image-2.jpg', "Expected new key to be test/test_image-2.jpg"

        # Now test for number skipping
        image_bytes3 = self.create_test_image(color='blue')
        key3 = 'test/test_image-10.jpg'
        s3.Object(self.bucket_name, key3).put(Body=image_bytes3)

        new_key = await self.s3_handler.number_matching_files(key1)
        print(new_key)
        assert new_key == 'test/test_image-11.jpg', "Expected new key to be test/test_image-11.jpg"

    # Test move_file
    async def test_move_file(self):
        image_bytes = self.create_test_image()
        filename = 'test_image.jpg'
        old_prefix = 'test'
        new_prefix = 'test2'

        s3 = boto3.resource("s3")
        s3.Object(self.bucket_name, f"{old_prefix}/{filename}").put(Body=image_bytes)

        result = await self.s3_handler.move_file(filename, old_prefix, new_prefix)
        print(result)
        assert result['old_key'] == f"{old_prefix}/{filename}", "Old key expected"
        assert result['new_key'] == f"{new_prefix}/{filename}", "New key expected"

        # verify file moved
        in_new_location = s3.Object(self.bucket_name, f"{new_prefix}/{filename}").get()
        assert in_new_location is not None, "File should exist in new location"

        # Verify file not in old location
        try:
            s3.Object(self.bucket_name, f"{old_prefix}/{filename}").get()
            assert False, "File should not exist in old location"
        except s3.meta.client.exceptions.NoSuchKey:
            assert True

    #test delete_image
    async def test_delete_image(self):
        s3 = boto3.resource("s3")
        filename = 'test_image.jpg'
        width = 4048
        height = 3036
        ratio = width/height
        image_bytes1 = self.create_test_image(width=width, height=height)
        image_bytes2 = self.create_test_image(width=2880, height=int(2880/ratio))
        image_bytes3 = self.create_test_image(width=300, height=int(300/ratio))

        group = 'test_delete_image'
        key1 = f"original/{group}/{filename}"
        key2 = f"fullsize/{group}/{filename}"
        key3 = f"thumb/{group}/{filename}"
        s3.Object(self.bucket_name, key1).put(Body=image_bytes1)
        s3.Object(self.bucket_name, key2).put(Body=image_bytes2)
        s3.Object(self.bucket_name, key3).put(Body=image_bytes3)

        results = await self.s3_handler.delete_image(group, filename)

        assert key1 in results['files'], f"{key1} not in files listed as deleted"
        assert key2 in results['files'], f"{key2} not in files listed as deleted"
        assert key3 in results['files'], f"{key3} not in files listed as deleted"

        object1 = s3.Object(self.bucket_name, key1)
        object2 = s3.Object(self.bucket_name, key2)
        object3 = s3.Object(self.bucket_name, key3)
        try:
            object1.get()
            object2.get()
            object3.get()
            assert False, "Expected objects to be deleted"
        except s3.meta.client.exceptions.NoSuchKey:
            assert True

    #test move_image
    async def test_move_image(self):
        s3 = boto3.resource("s3")
        filename = 'test_image.jpg'
        width = 4048
        height = 3036
        ratio = width/height
        image_bytes1 = self.create_test_image(width=width, height=height)
        image_bytes2 = self.create_test_image(width=2880, height=int(2880/ratio))
        image_bytes3 = self.create_test_image(width=300, height=int(300/ratio))

        group1 = 'test_group_image1'
        group2 = 'test_group_image2'
        key1 = f"original/{group1}/{filename}"
        key2 = f"fullsize/{group1}/{filename}"
        key3 = f"thumb/{group1}/{filename}"
        s3.Object(self.bucket_name, key1).put(Body=image_bytes1)
        s3.Object(self.bucket_name, key2).put(Body=image_bytes2)
        s3.Object(self.bucket_name, key3).put(Body=image_bytes3)

        results = await self.s3_handler.move_image(group1, group2, filename)
        print(results)

        for result in results:
            assert result['old_key'] != result['new_key'], "File not moved in results"
            new_key = result['new_key']
            object = s3.Object(self.bucket_name, new_key)
            assert object.get(), "File in new location not found"

        object1 = s3.Object(self.bucket_name, key1)
        object2 = s3.Object(self.bucket_name, key2)
        object3 = s3.Object(self.bucket_name, key3)

        try:
            object1.get()
            object2.get()
            object3.get()
            assert False, "Expected objects to be deleted"
        except s3.meta.client.exceptions.NoSuchKey:
            assert True

    # test check_and_rename_file
    async def test_check_and_rename_file(self):
        s3 = boto3.resource("s3")
        prefix = 'test_check_and_rename'
        filename = 'test_image.jpg'
        image_bytes = self.create_test_image()
        s3.Object(self.bucket_name, f"{prefix}/{filename}").put(Body=image_bytes)

        results = await self.s3_handler.check_and_rename_file(prefix, filename)
        print(results)
        assert results == f"{prefix}/test_image-1.jpg", "Expected file to be renamed to test_image-1.jpg"



    async def test_presign_file(self):
        filename = 'test1.jpg'
        group = 'test_presign_file'

        results = await self.s3_handler.presign_file(f"{group}/{filename}")
        assert 'presigned_url' in results, "There must be a presigned URL"

    #test upload_image
    async def test_process_image(self):
        filename = 'test_image.jpg'
        width = 4048
        height = 3036
        group = 'test_process_image'

        gps_ifd = {
            piexif.GPSIFD.GPSVersionID: (2, 0, 0, 0),
            piexif.GPSIFD.GPSLatitudeRef: 'N',
            piexif.GPSIFD.GPSLatitude: [(123, 1), (45,1), (500000, 10000)],
            piexif.GPSIFD.GPSLongitudeRef: 'W',
            piexif.GPSIFD.GPSLongitude: [(123, 1), (45,1), (500000, 10000)],
        }
        image_bytes = self.create_test_image(width=width, height=height, gps_data=gps_ifd)
        s3 = boto3.resource("s3")
        s3.Object(self.bucket_name, f"original/{group}/{filename}").put(Body=image_bytes)
        results = await self.s3_handler.process_image(group, filename)

        print(results)
        assert 'files' in results, 'Files not in results'


        #check for results in API response
        assert f"fullsize/{group}/{filename}" in results['files'], "Fullsize name doesn't match"
        assert f"thumb/{group}/{filename}" in results['files'], "Thumbnail name doesn't match"

        #check for fullsize
        object = s3.Object(self.bucket_name, f"fullsize/{group}/{filename}")
        image = object.get()
        assert image, "Fullsize File in new location not found"
        #check if fullsize is resized
        fullsize = Image.open(image['Body'])
        assert fullsize.width == self.s3_handler.fullsize_side, "Not resized to fullsize image size"

        #check for thumbnail
        object = s3.Object(self.bucket_name, f"thumb/{group}/{filename}")
        image = object.get()
        assert image, "Thumbnail File in new location not found"
        thumb = Image.open(image['Body'])
        assert thumb.width == self.s3_handler.thumbnail_side, "Not resized to thumbnail size"

        #check for date and coordinates
        assert 'data' in results, "Date and coordinates not in results"




