from unittest.mock import MagicMock
from io import BytesIO, BufferedReader
from PIL import Image
import pytest
from mongomock import MongoClient
from datetime import datetime, timezone
from http import HTTPStatus

from app.main import app, add_images_to_group
from app.db import connect_to_db

# test get_images
def test_get_images(client, mock_mongodb_image_groups_initialized, get_group_id):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    response = client.get("/image_groups/" + str(get_group_id))

    json = response.json()
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

def test_delete_group(client, mock_mongodb_image_groups_initialized, get_group_id):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
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


ImageHandler = MagicMock()
ImageHandler.return_value.get_date_and_coords.return_value = {
    'DateTime': datetime.now(timezone.utc),
    'coords':{
        'latitude': 1.23,
        'longitude': 45.6
    }
}

# test add_images_to_group the one that's shared by upload_images and upload_images_to_group
@pytest.mark.asyncio
async def test_add_images_to_group(get_group_id):
    mock_mongoclient = MongoClient()
    mock_mongodb = mock_mongoclient.db
    mock_upload_images = [
        MockUploadImage('test1.jpeg', create_dummy_image('test1','jpeg')),
        MockUploadImage('test2.jpeg', create_dummy_image('test2','jpeg')),
    ]


    image_data = await add_images_to_group(get_group_id, mock_upload_images, mock_mongodb)
    print(image_data)
    assert len(image_data) == len(mock_upload_images)
    assert image_data[0]['filename'] == 'test1.jpeg', "Unexpected filename"
    assert image_data[1]['filename'] == 'test2.jpeg', "Unexpected filename"
# test upload_images the one that creates a new group
def test_upload_images(client, mock_mongodb):
    app.dependency_overrides[connect_to_db] = mock_mongodb
    mock_upload_images = [
        ('images',create_dummy_image_buffered_reader('test1','jpeg')),
        ('images',create_dummy_image_buffered_reader('test2','jpeg')),
    ]

    print('mock_upload_images:', mock_upload_images)
    response = client.post("/image_groups/", data={'name':'test'}, files=mock_upload_images)
    print('request:', response.request)
    json = response.json()
    assert response.status_code == HTTPStatus.OK
    assert 'images' in json and len(json['images']) > 0, "No images in group" # check if images are present
# test upload_images_to_group the one that adds images to an existing group
def test_upload_images_to_group(client, get_group_id, mock_mongodb_image_groups_initialized):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    mock_upload_images = [
        ('images',create_dummy_image_buffered_reader('test1','jpeg')),
        ('images',create_dummy_image_buffered_reader('test2','jpeg')),
    ]

    print('mock_upload_images:', mock_upload_images)
    response = client.post("/images/" + str(get_group_id), files=mock_upload_images)
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

def test_edit_image(client, mock_mongodb_image_groups_initialized, get_image_id1, get_group2_id):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized

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

def test_edit_image_upload(client, mock_mongodb_image_groups_initialized, get_image_id1):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized

    filehandle = 'test1'
    mock_upload_image = ('image',create_dummy_image_buffered_reader(filehandle,'jpeg')),


    print('mock_upload_image:', mock_upload_image)
    response = client.patch("/images/" + str(get_image_id1) + "/file", files=mock_upload_image)
    json = response.json()
    print('json:', json)
    assert response.status_code == HTTPStatus.OK
    assert json['filename'] == f"{filehandle}.jpeg", "Filename not updated"
def test_edit_image_upload_404(client, mock_mongodb_image_groups_initialized):
    # we're using our mock_mongodb_image_groups_initialized fixture which has image_groups and images initialized
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized
    filehandle = 'test1'
    mock_upload_image = ('image',create_dummy_image_buffered_reader(filehandle,'jpeg')),
    response = client.patch("/images/" + 'bbbbbbbbbbbbbbbbbbbbbbbb' + '/file', files=mock_upload_image)

    assert response.status_code == HTTPStatus.NOT_FOUND

def test_delete_image(client, mock_mongodb_image_groups_initialized, get_image_id1):
    app.dependency_overrides[connect_to_db] = mock_mongodb_image_groups_initialized

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

