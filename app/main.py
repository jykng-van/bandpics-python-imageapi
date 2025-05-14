from fastapi import FastAPI, UploadFile, HTTPException, Depends, Body, Form, File
from fastapi.encoders import jsonable_encoder
from http import HTTPStatus

from app.image_handler import ImageHandler
#from maps_info import MapsInfo
from PIL import Image
from bson.objectid import ObjectId

import io
from datetime import datetime, timezone

from app.db import lifespan, connect_to_db
from app.models import ImageGroup, ImageData, UpdateImageData
from typing_extensions import Annotated

app = FastAPI(lifespan=lifespan) # start FastAPI with lifespan
print('app:',app)
@app.get("/")
async def read_root():
    return {"Hello": "World"}

################### IMAGE GROUPS ###################
# Upload images to the server
# This endpoint will create a new group of images and return the group id and the images with their coordinates and date
@app.post("/image_groups")
@app.post("/image_groups/", response_description="Upload images and create a new image_group")
async def upload_images(name:str = Form(...), images: list[UploadFile]=File(...), db=Depends(connect_to_db)):
    print('Images:', images)
    print('Number of images:', len(images))

    # Add group here
    groups_collection = db.get_collection('image_groups')
    name = name if not None else datetime.now().strftime("%Y-%m-%d") # Default name as current date
    # prepare for insertion
    image_group = {
        'name': name,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc)
    }
    inserted_group = groups_collection.insert_one(image_group)
    collection_id = inserted_group.inserted_id # get group id
    print(collection_id)

    # add images to group
    if len(images) > 0:
        image_data = await add_images_to_group(str(collection_id), images, db)
    else:
        image_data = []

    # output group id and name and images
    return {
        'images': image_data,
        'group_id': str(collection_id),
        'name':name
    }
# add images to a group, used in upload_images and add to group
async def add_images_to_group(group_id: str, images: list[UploadFile], db):
    print('Number of images:', len(images))
    print('db:', db)
    print(images)
    images_collection = db.get_collection('images')
    image_data = []
    group = ObjectId(group_id) # convert to ObjectId
    print('Group:', group)

    # process each of the images
    for upload_image in images:
        image_content = await upload_image.read() # read image content
        image = Image.open(io.BytesIO(image_content)) # open image content converted to bytes
        print('Filename:', upload_image.filename)
        image_handler = ImageHandler(image) # create ImageHandler

        date_and_coords = image_handler.get_date_and_coords() #get dat and coordinates from image
        print('Date and coords:', date_and_coords)

        # insert into db
        inserted_image = images_collection.insert_one({
            'filename': upload_image.filename,
            'data': date_and_coords,
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
            'group': group
        })

        image_data.append({
            '_id': str(inserted_image.inserted_id),
            'filename': upload_image.filename,
            'data': date_and_coords,
        }) # add results to image_data list
    return image_data # return the list of images

# Get all images in a group
@app.get("/image_groups/{group_id}", response_model=ImageGroup, response_model_by_alias=False, response_model_exclude_none=True,
         response_description="Get the image_group and all of its images")
async def get_images(group_id: str, db = Depends(connect_to_db)):
    group_collection = db.get_collection('image_groups')
    print(group_id, db)

    # pipeline to get group and all its images
    pipeline = [
        {
            '$match':{ #match group id in image_groups
                '_id': ObjectId(group_id)
            }
        },
        {
            '$lookup': { #lookup/join images collections to image_groups
                'from': 'images', # using images collection
                'localField': '_id', # on group id
                'foreignField': 'group', # with group field in images collection
                'as': 'images' # results as the images field in image_groups
            }
        },
        {
            '$project':{
                'images.group':0 #exclude group field in images
            }
        }
    ]
    cursor = group_collection.aggregate(pipeline=pipeline) # run aggregate query
    group_list = list(cursor) # convert cursor to list
    if len(group_list) > 0:
        group = group_list[0] # get the first group which there probably should only be one
        print('image group', group)
        return group
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Group with that ID not found")

# Edit a group of images
@app.patch("/image_groups/{group_id}", response_model=ImageGroup, response_model_by_alias=False, response_model_exclude_none=True,
         response_description="Edit an image_group")
async def edit_group(group_id: str, group:Annotated[ImageGroup, Body(embed=True)], db=Depends(connect_to_db)):
    print('Group:', group)
    print(db)

    group_collection = db.get_collection('image_groups')
    group_id = ObjectId(group_id) # convert to ObjectId

    group.created_at = None #remove created_at
    #exclude None values from the group
    group = {
        k: v for k, v in group.model_dump(by_alias=True).items() if v is not None
    }
    print('Group:', group)
    if (len(group) > 0):
        #group['updated_at'] = datetime.now(timezone.utc)
        print('Group:', group)
        update_result = group_collection.find_one_and_update(
            {'_id': group_id}, # find group by id
            {'$set': group}, # set group values
            return_document= True # return the updated group
        )
        print('Update result:', update_result)
        if update_result is not None:
            return update_result
        else:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Group with that ID not found")
    if (existing_group := group_collection.find_one({'_id': group_id})) is not None:
        return existing_group
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Group with that ID not found")

@app.delete("/image_groups/{group_id}", response_description="Delete an image_group and all of its images")
async def delete_group(group_id:str, db=Depends(connect_to_db)):
    group_id = ObjectId(group_id) # convert to ObjectId

    group_collection = db.get_collection('image_groups')
    image_collection = db.get_collection('images')

    result = {}

    #delete group first getting the group with name and id
    if (group := group_collection.find_one_and_delete({'_id': group_id})) is not None:
        result['image_group'] = {
            '_id': str(group['_id']),
            'name': group.get('name', 'Group')
        }

    #find images
    images = list(image_collection.find({'group': group_id}))

    result['num_images'] = len(images)
    #more for deleting the image files
    result['removed'] = []
    for image in images:
        result['removed'].append(image['filename'])

    #delete images in group
    image_collection.delete_many({'group': group_id})

    return result

################### IMAGES ###################
# Add images to an existing group
@app.post("/images/{group_id}", response_description="Upload images to a group")
async def upload_images_to_group(group_id: str, images: list[UploadFile]=File(...), db=Depends(connect_to_db)):
    group_id = ObjectId(group_id) # convert to ObjectId
    print('Group:', group_id)

    group_collection = db.get_collection('image_groups')
    if (group := group_collection.find_one({'_id': group_id})) is not None:
        # add images to group
        if len(images) > 0:
            image_data = await add_images_to_group(str(group_id), images, db)
        else:
            image_data = []

        return {
            'added_images': image_data,
            'group_id': str(group_id),
            'name': group.get('name', 'Group')
        }
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Group with that ID not found")

@app.get("/images/{image_id}", response_model=ImageData, response_model_by_alias=False, response_model_exclude_none=True,
    response_description="Get image by id")
async def get_image(image_id: str, db=Depends(connect_to_db)):
    image_id = ObjectId(image_id) # Convert to ObjectId
    image_collection = db.get_collection('images')

    if (image := image_collection.find_one({'_id': image_id})) is not None:
        print(image)
        return image
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Image with that ID not found")

@app.patch("/images/{image_id}", response_model=ImageData, response_model_by_alias=False, response_model_exclude_none=True,
    response_description="Edit an image of that id, description and group to change")
async def edit_image(image_id: str, data:Annotated[UpdateImageData, Body(embed=True)], db=Depends(connect_to_db)):
    image_id = ObjectId(image_id) # Convert to ObjectId
    image_collection = db.get_collection('images')

    #exclude None values from the image
    data = {
        k: v for k, v in data.model_dump(by_alias=True).items() if v is not None
    }

    if (len(data) > 0):
        if 'group' in data:
            data['group'] = ObjectId(data['group'])
        data_result = image_collection.find_one_and_update({'_id': image_id}, {'$set': data}, return_document=True) # update image
        if data_result is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Image with that ID not found")
    else:
        data_result = image_collection.find_one({'_id': image_id})

    return data_result

@app.patch("/images/{image_id}/file", response_model=ImageData, response_model_by_alias=False, response_model_exclude_none=True,
    response_description="Edit an image of that id")
async def replace_image(image_id: str, image:UploadFile, db=Depends(connect_to_db)):
    print('Image:', image)
    image_id = ObjectId(image_id) # Convert to ObjectId
    image_collection = db.get_collection('images')


    image_content = await image.read() # read image content
    image_data = Image.open(io.BytesIO(image_content)) # open image content converted to bytes
    print('Filename:', image.filename)
    image_handler = ImageHandler(image_data) # create ImageHandler

    date_and_coords = image_handler.get_date_and_coords() #get dat and coordinates from image
    print('Date and coords:', date_and_coords)
    data = {
        'filename': image.filename,
        'data': date_and_coords,
        'updated_at': datetime.now(timezone.utc),
    }

    image_result = image_collection.find_one_and_update({'_id': image_id}, {'$set': data}, return_document=True) # update image
    if image_result is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Image with that ID not found")

    return image_result

@app.delete("/images/{image_id}", response_model=ImageData, response_model_by_alias=False, response_model_exclude_none=True,
            response_description="Delete an image")
async def delete_image(image_id:str, db=Depends(connect_to_db)):
    image_id = ObjectId(image_id) # convert to ObjectId

    image_collection = db.get_collection('images')

    result = image_collection.find_one_and_delete({'_id': image_id})
    if result is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Image with that ID not found")

    return result
