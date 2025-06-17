from pytest import fixture
from unittest.mock import MagicMock, AsyncMock
from mongomock import MongoClient
from fastapi.testclient import TestClient
from bson import ObjectId
from datetime import datetime

class MockMongoClient:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *args):
        pass

    def get_collection(self, name): # Mocking get_collection because the MockMongoClient doesn't have it
        return self.db.get_collection(name)

#empty db for testing
@fixture
def mock_mongodb():
    def mock_get_mongodb():
        from app.main import app
        mock_client = MongoClient()

        app.db = mock_client.db #to set the app's db to the mock db

        return MockMongoClient(mock_client.db)

    return mock_get_mongodb

test_group_id = ObjectId('aaaaaaaaaaaaaaaaaaaaaaa1')
test_image1_id = ObjectId('aaaaaaaaaaaaaaaaaaaaaaa2')
test_image2_id = ObjectId('aaaaaaaaaaaaaaaaaaaaaaa3')
test_group2_id = ObjectId('aaaaaaaaaaaaaaaaaaaaaaa4')
test_created_at = datetime(2025,1,1,0,0,0)
test_image_data = {
    'coords':{
        'latitude':1.23,
        'longitude':45.6
    }
}
test_image_group = {
    'name':'test',
    '_id': test_group_id,
    'created_id':test_created_at,
    'updated_at':test_created_at,
}

test_images = [
    {
        '_id': test_image1_id,
        'filename':'img1.jpg',
        'data': test_image_data,
        'group': test_group_id,
        'created_id':test_created_at,
        'updated_at':test_created_at,
    },
    {
        '_id': test_image2_id,
        'filename':'img2.jpg',
        'data': test_image_data,
        'group': test_group_id,
        'created_id':test_created_at,
        'updated_at':test_created_at,
    }
]

test_image_group2 = {
    'name':'test2',
    '_id': test_group2_id,
    'created_id':test_created_at,
    'updated_at':test_created_at,
}

# DB with images groups and images for testing
@fixture
def mock_mongodb_image_groups_initialized():
    def mock_get_mongodb():
        from app.main import app

        print('mock mongo image groups initialized')
        mock_client = MongoClient()

        mock_client.db.image_groups.insert_one(test_image_group)
        mock_client.db.images.insert_many(test_images)
        mock_client.db.image_groups.insert_one(test_image_group2)

        app.db = mock_client.db #to set the app's db to the mock db

        return MockMongoClient(mock_client.db)

    return mock_get_mongodb


@fixture
def client():
    # we patch auth within our client fixture
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()

@fixture
def get_group_id():
    return test_group_id
@fixture
def get_image_id1():
    return test_image1_id
@fixture
def get_image_id2():
    return test_image2_id
@fixture
def get_group2_id():
    return test_group2_id
@fixture
def mock_executor():
    def mock_get_executor():
        return MagicMock()

    return mock_get_executor

def mock_upload_image(*args, **kwargs):
    group = args[0]
    filename = args[1]
    return {
        'filename':filename,
        'files':[
            f"{group}/original/{filename}",
            f"{group}/fullsize/{filename}",
            f"{group}/thumb/{filename}"
        ]
    }
def mock_presign_file(*args, **kwargs):
    group = args[0]
    filename = args[1]
    return {
        'presigned_url': f'https://example.com/{group}/{filename}'
    }
async def mock_prepare_upload_single_image(*args, **kwargs):
    group = args[0]
    filename = args[1]
    return {
        '_id': f"id_{group}_{filename}",
        'filename': filename,
        'presigned_url': f"https://example.com/{group}/{filename}",
        #'files':fileinfo['files'],
        #'data': date_and_coords,
    }
@fixture
def mock_s3_handler():

    def mock_get_s3_handler():
        s3 = MagicMock()
        s3.upload_image = AsyncMock(side_effect=mock_upload_image)
        s3.move_image = AsyncMock()
        s3.delete_image = AsyncMock()
        return s3
    return mock_get_s3_handler