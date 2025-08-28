from unittest.mock import MagicMock, AsyncMock
from io import BytesIO, BufferedReader
from PIL import Image
import pytest
from mongomock import MongoClient
from datetime import datetime, timezone
from http import HTTPStatus
from tests.conftest import mock_presign_file, mock_prepare_upload_single_image
from bson.objectid import ObjectId

from app.main import app, add_images_to_group, prepare_upload_single_image, setup_s3_handler, process_s3_image, handler
from app.db import connect_to_db

# test get_images
def test_get_images(client, mock_mongodb_image_groups_initialized, get_group_id):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    response = client.get("/image_groups/" + str(get_group_id))

    json = response.json()
    print(json)
    assert response.status_code == HTTPStatus.OK
    assert json['name'] == 'test', "Unexpected group name" # check if group name is correct
    assert 'images' in json and len(json['images']) > 0, "No images in group" # check if images are present
def test_get_images_404(client, mock_mongodb_image_groups_initialized):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    response = client.get("/image_groups/" + 'bbbbbbbbbbbbbbbbbbbbbbbb')

    assert response.status_code == HTTPStatus.NOT_FOUND


group_changes = {'group':
    {
        'name': 'new name',
        'description': 'new description'
    }
}
# test list groups
def test_get_image_groups(client, mock_mongodb_image_groups_initialized):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized

    response = client.get("/image_groups/")
    json = response.json()
    assert response.status_code == HTTPStatus.OK
    assert len(json) > 0, "No image groups found"
    assert len(json) >= 2, "Not all groups found"
def test_get_image_groups_by_event(client, mock_mongodb_image_groups_initialized, get_event_id):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized


    response = client.get(f"/image_groups/?event={str(get_event_id)}")
    json = response.json()
    print(json)
    assert response.status_code == HTTPStatus.OK
    assert len(json) == 1, "More than the filtered groups selected"
    assert json[0]['event'] == str(get_event_id), "Filtered group id doesn't match"
    assert len(json[0]['images']) > 0, "Images in group"
    assert 'id' in json[0]['images'][0], "Image does not have id"

# test edit_group
def test_edit_group(client, mock_mongodb_image_groups_initialized, get_group_id):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized

    response = client.patch("/image_groups/" + str(get_group_id), json=group_changes)
    json = response.json()
    print('json:', json)
    assert response.status_code == HTTPStatus.OK
    assert json['name'] == group_changes['group']['name'], "Group name not updated"
    assert json['description'] == group_changes['group']['description'], "Group description not updated"
    assert json['updated_at'] != json['created_at'], "Updated at not changed" # check if updated_at is different from created_at
def test_edit_images_404(client, mock_mongodb_image_groups_initialized):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized

    response = client.patch("/image_groups/" + 'bbbbbbbbbbbbbbbbbbbbbbbb', json=group_changes)

    assert response.status_code == HTTPStatus.NOT_FOUND

def test_delete_group(client, mock_mongodb_image_groups_initialized, get_group_id, mock_s3_handler):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    app.dependency_overrides[setup_s3_handler] = mock_s3_handler
    response = client.delete("/image_groups/" + str(get_group_id))

    json = response.json()
    assert response.status_code == HTTPStatus.OK
    assert json['image_group']['_id'] == str(get_group_id), "group id doesn't match" # check if group id is correct
    assert json['num_images'] == 2, "num_images deleted doesn't match" # check number of images deleted

    #check if the group and the images are deleted
    db = app.db
    group_collection = db.get_collection('image_groups')
    group = group_collection.find_one({'_id': get_group_id})
    assert group is None, "Group not deleted"

    image_collection = db.get_collection('images')
    images = list(image_collection.find({'group': get_group_id}))
    assert len(images) == 0, "Images not deleted"

def test_delete_group_not_found(client, mock_mongodb_image_groups_initialized):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized

    response = client.delete("/image_groups/" + 'bbbbbbbbbbbbbbbbbbbbbbbb')
    json = response.json()

    assert response.status_code == HTTPStatus.OK
    assert 'image_group' not in json
    assert json['num_images'] == 0

def test_remove_associated_event(client, mock_mongodb_image_groups_initialized, get_event_id):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized

    response = client.patch(f"/events/{str(get_event_id)}/image_groups")
    json = response.json()
    print(json)
    assert response.status_code == HTTPStatus.OK
    assert json['modified_count'] == 1, "Image groups affected not 1"

    #check if there are no groups with the event
    db = app.db
    group_collection = db.get_collection('image_groups')
    cursor = group_collection.find({'event': get_event_id})
    groups = list(cursor)
    assert len(groups) == 0, "Event not removed from groups"


# Dummy image creation
def create_dummy_image_buffer(filename, file_type: str = "jpeg"):
    image_buffer = BytesIO()
    image = Image.new("RGB", (100, 100))
    image.save(image_buffer, file_type)
    image_buffer.name = f"{filename}.{file_type}"
    image_buffer.seek(0)
    return image_buffer
def create_dummy_image(filename, file_type: str = "jpeg"):
    image_buffer = create_dummy_image_buffer(filename, file_type)
    return image_buffer.read()
def create_dummy_image_buffered_reader(filename, file_type: str = "jpeg"):
    image_buffer = create_dummy_image_buffer(filename, file_type)
    buffered_reader = BufferedReader(image_buffer)
    return buffered_reader


# Mock class for UploadFile images
class MockUploadImage:
    def __init__(self, filename: str, file: BytesIO):
        self.filename = filename
        self.file = file
    async def read(self):
        return self.file


ImageDataHandler = MagicMock()
ImageDataHandler.return_value.get_date_and_coords.return_value = {
    'DateTime': datetime.now(timezone.utc),
    'coords':{
        'latitude': 1.23,
        'longitude': 45.6
    }
}

# test upload an image
@pytest.mark.asyncio
async def test_prepare_upload_single_image(get_group_id):
    mock_mongoclient = MongoClient()
    mock_mongodb = mock_mongoclient.db
    #mock_image = MockUploadImage('test1.jpeg', create_dummy_image('test1','jpeg'))
    images_collection = mock_mongodb.get_collection('image_collection')

    #mock s3 related functions
    s3 = AsyncMock()
    s3.check_and_rename_file = AsyncMock(return_value=f"original/{get_group_id}/test1.jpeg")
    presigned_url = 'https://example.com/{get_group_id}/test1.jpeg'
    s3.presign_file = AsyncMock(return_value={'presigned_url':presigned_url, 'type': 'image/jpeg'})
    image_data = await prepare_upload_single_image(ObjectId(get_group_id), 'test1.jpeg', images_collection, s3)
    print(image_data)
    assert '_id' in image_data, 'Image id expected in results'
    assert 'presigned_url' in image_data, 'Presigned URL expected in results'
    assert image_data['presigned_url'] == presigned_url, 'Presigned URL does not match'


# test add_images_to_group the one that's shared by upload_images and upload_images_to_group
@pytest.mark.asyncio
async def test_add_images_to_group(get_group_id):
    mock_mongoclient = MongoClient()
    mock_mongodb = mock_mongoclient.db
    mock_upload_filenames = [
        'test1.jpeg',
        'test2.jpeg',
    ]

    #mock s3 related functions
    s3 = MagicMock()
    s3.check_and_rename_file = AsyncMock(side_effect=lambda prefix, filename: f"{prefix}/{filename}")
    s3.presign_file = AsyncMock(side_effect=mock_presign_file)

    image_data = await add_images_to_group(get_group_id, mock_upload_filenames, mock_mongodb, s3)
    print(image_data)
    assert len(image_data) == len(mock_upload_filenames)
    assert image_data[0]['filename'] == f"{get_group_id}/test1.jpeg", "Unexpected filename"
    assert 'presigned_url' in image_data[0], "Presigned URL expected"
    assert image_data[1]['filename'] == f"{get_group_id}/test2.jpeg", "Unexpected filename"
    assert 'presigned_url' in image_data[1], "Presigned URL expected"

# test upload_images the one that creates a new group
def test_upload_images(client, mock_mongodb, mock_s3_handler, mocker):
    app.dependency_overrides[connect_to_db] = mock_mongodb
    app.dependency_overrides[setup_s3_handler] = mock_s3_handler
    mock_upload_images = [
        'test1.jpeg',
        'test2.jpeg',
    ]

    print('mock_upload_images:', mock_upload_images)
    data = {'group':{
        'name':'test',
        'images': mock_upload_images,
        'event':'eeeeeeeeeeeeeeeeeeeeeee1'
    }}

    mocker.patch('app.main.prepare_upload_single_image', mock_prepare_upload_single_image)
    response = client.post("/image_groups/", json=data)
    print('request:', response.request)
    json = response.json()
    print(json)
    assert response.status_code == HTTPStatus.OK
    assert 'images' in json and len(json['images']) > 0, "No images in group" # check if images are present
# test upload_images_to_group the one that adds images to an existing group
@pytest.mark.asyncio
async def test_upload_images_to_group(client, get_group_id, mock_mongodb_image_groups_initialized, mock_s3_handler):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    app.dependency_overrides[setup_s3_handler] = mock_s3_handler
    mock_image_files = [
        'test1.jpeg',
        'test2.jpeg'
    ]

    print('mock_image_files:', mock_image_files)

    response = client.post("/images/" + str(get_group_id), json={'images': mock_image_files})
    json = response.json()
    print('json:', json)
    assert response.status_code == HTTPStatus.OK
    assert 'added_images' in json and len(json['added_images']) == 2, "Images not added" # check if images are present

    #check if there's 4 images in the group
    db = app.db
    print('db:',db)
    collection = db.get_collection('images')
    images = list(collection.find({'group': get_group_id}))
    print('images:', images)
    assert len(images) == 4, "Images not added to group"

def test_get_image(client, mock_mongodb_image_groups_initialized, get_image_id1):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized

    response = client.get("/images/" + str(get_image_id1))
    json = response.json()

    assert response.status_code == HTTPStatus.OK
    assert json['filename'] == 'img1.jpg', 'Filename not correct'
def test_get_image_404(client, mock_mongodb_image_groups_initialized):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    response = client.get("/images/" + 'bbbbbbbbbbbbbbbbbbbbbbbb')

    assert response.status_code == HTTPStatus.NOT_FOUND

def test_edit_image(client, mock_mongodb_image_groups_initialized, get_image_id1, get_group2_id, mock_s3_handler):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    app.dependency_overrides[setup_s3_handler] = mock_s3_handler

    new_description = 'New description'
    image_changes = {
        'data':{
            'description': new_description,
            'group': str(get_group2_id)
        }
    }
    response = client.patch("/images/" + str(get_image_id1), json=image_changes)
    json = response.json()

    assert response.status_code == HTTPStatus.OK
    assert json['description'] == new_description, 'Description not updated'
    assert json['group'] == str(get_group2_id), 'Group not updated'
def test_edit_image_404(client, mock_mongodb_image_groups_initialized):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    image_changes = {
        'data':{
            'description':'test'
        }
    }
    response = client.patch("/images/" + 'bbbbbbbbbbbbbbbbbbbbbbbb', json=image_changes)

    assert response.status_code == HTTPStatus.NOT_FOUND

def test_edit_image_upload(client, mock_mongodb_image_groups_initialized, get_image_id1, mock_s3_handler, mocker):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    app.dependency_overrides[setup_s3_handler] = mock_s3_handler

    filehandle = 'test1'
    mock_filename = 'test1.jpeg'

    #print('mock_upload_image:', mock_upload_image)
    mocker.patch('app.main.prepare_upload_single_image', mock_prepare_upload_single_image)
    response = client.patch("/images/" + str(get_image_id1) + "/file", json={'image':mock_filename})
    json = response.json()
    print('json:', json)
    assert response.status_code == HTTPStatus.OK
    assert json['filename'] == f"{filehandle}.jpeg", "Filename not updated"
def test_edit_image_upload_404(client, mock_mongodb_image_groups_initialized):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    filehandle = 'test1'
    #mock_upload_image = create_dummy_image(filehandle,'jpeg')
    mock_filename = 'test1.jpeg'
    response = client.patch("/images/" + 'bbbbbbbbbbbbbbbbbbbbbbbb' + '/file', json={'image':mock_filename})

    assert response.status_code == HTTPStatus.NOT_FOUND

def test_delete_image(client, mock_mongodb_image_groups_initialized, get_image_id1, mock_s3_handler):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    app.dependency_overrides[setup_s3_handler] = mock_s3_handler

    response = client.delete("/images/" + str(get_image_id1))
    json = response.json()
    assert response.status_code == HTTPStatus.OK
    assert json['id'] == str(get_image_id1), "Image id donsn't match"

    #check if the image was deleted
    db = app.db

    image_collection = db.get_collection('images')
    image = image_collection.find_one({'_id': get_image_id1})
    assert image is None, "Image not deleted"
def test_delete_image_404(client, mock_mongodb_image_groups_initialized):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized

    response = client.delete("/images/" + 'bbbbbbbbbbbbbbbbbbbbbbbb')

    assert response.status_code == HTTPStatus.NOT_FOUND
def make_s3_event(group_id, filename):
    return {'Records':
        [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'us-west-2', 'eventTime': '2025-01-01T01:01:01.000Z',
          'eventName': 'ObjectCreated:Put',
          'userIdentity': {'principalId': 'AWS:AID234DASDFASDF'},
          'requestParameters': {'sourceIPAddress': '127.0.0.1'},
          'responseElements': {'x-amz-request-id': 'X', 'x-amz-id-2': 'A9/s+aaaaa+aaaaa'},
          's3': {
              's3SchemaVersion': '1.0',
              'configurationId': 'image_uploaded',
              'bucket': {'name': 'test_bucket', 'ownerIdentity': {'principalId': 'AAAAA'}, 'arn': 'arn:aws:s3:::test'},
              'object': {'key': f"original/{group_id}/{filename}", 'size': 1024, 'eTag': 'eTAG', 'sequencer': 'asdfasdfasdf'}}}]}
@pytest.mark.asyncio
async def test_process_image(get_group_id, generate_mock_mongodb_image_groups_initialized, mock_s3_handler, mocker):
    filename = 'img1.jpg'
    # Mocked S3 event
    event = make_s3_event(get_group_id, filename)
    context = MagicMock()

    mocker.patch('app.main.connect_to_db', generate_mock_mongodb_image_groups_initialized)
    #app.dependency_overrides[connect_to_db] = generate_mock_mongodb_image_groups_initialized
    mocker.patch('app.main.S3Handler', mock_s3_handler)

    image_data = await process_s3_image(event, context)
    print('image_data:', image_data)

    assert image_data['filename'] == filename, "Filename does not match"
    assert 'filename' in image_data, "Data not found"
    assert 'data' in image_data, "Data not found"

def test_handler(get_group_id, generate_mock_mongodb_image_groups_initialized, mock_s3_handler, mocker):
    filename = 'img1.jpg'
    # Mocked S3 event
    event = make_s3_event(get_group_id, filename)
    context = MagicMock()

    mocker.patch('app.main.connect_to_db', generate_mock_mongodb_image_groups_initialized)
    #app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    mocker.patch('app.main.S3Handler', mock_s3_handler)

    image_data = handler(event, context)
    print('image_data:', image_data)
    assert image_data['filename'] == filename, "Filename does not match"
    assert 'filename' in image_data, "Data not found"
    assert 'data' in image_data, "Data not found"

