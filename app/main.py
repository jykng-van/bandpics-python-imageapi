from fastapi import FastAPI, UploadFile, HTTPException, Depends, Body, Form, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from http import HTTPStatus

from app.image_data_handler import ImageDataHandler
#from maps_info import MapsInfo
from PIL import Image
from bson.objectid import ObjectId

import io
from datetime import datetime, timezone

from app.db import lifespan, connect_to_db
from app.models import ImageGroup, ImageData, UpdateImageData
from typing_extensions import Annotated

from app.s3_handler import S3Handler

from mangum import Mangum # Use mangum for AWS

from starlette.requests import Request

import asyncio
import concurrent.futures

app = FastAPI(lifespan=lifespan) # start FastAPI with lifespan
print('app:',app)

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    #allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def setup_s3_handler(): #prepare the S3 handler by dependency injection
    s3 = S3Handler()
    yield s3

@app.get("/")
async def read_root():
    return {"Hello": "World"}

@app.post("/")
async def hello(request: Request):
    print('Request:',request)
    return {"aws_event": request.scope["aws.event"]}

################### IMAGE GROUPS ###################
# Get all image groups
@app.get("/image_groups/")
@app.get("/image_groups", response_model=list[ImageGroup], response_model_by_alias=False, response_model_exclude_none=True,
         response_description="Get all image_groups")
async def get_image_groups(db=Depends(connect_to_db)) -> list[ImageGroup]:
    groups_collection = db.get_collection('image_groups')
    groups = groups_collection.find({})
    group_list = list(groups)
    return group_list


# Upload images to the server
# This endpoint will create a new group of images and return the group id and the images with their coordinates and date
@app.post("/image_groups/")
@app.post("/image_groups", response_description="Upload images and create a new image_group")
async def upload_images(name:str = Form(...), images: list[str] = Form(...), db=Depends(connect_to_db), s3=Depends(setup_s3_handler)):
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
        image_data = await add_images_to_group(str(collection_id), images, db, s3)
    else:
        image_data = []

    # output group id and name and images
    return {
        'images': image_data,
        'group_id': str(collection_id),
        'name':name
    }
# add images to a group, used in upload_images and add to group
async def add_images_to_group(group_id: str, images: list[str], db, s3):
    print('Number of images:', len(images))
    print('db:', db)
    print(images)
    images_collection = db.get_collection('images')
    image_data = []
    group = ObjectId(group_id) # convert to ObjectId
    print('Group:', group)

    # process each of the images
    for image in images:
        uploaded = await prepare_upload_single_image(group, image, images_collection, s3)
        image_data.append(uploaded)
    return image_data # return the list of images

async def prepare_upload_single_image(group: ObjectId, filename: str, images_collection, s3, image_id:ObjectId = None):
    """ image_content = await image.read() # read image content
    pil_image = Image.open(io.BytesIO(image_content)) # open image content converted to bytes
    print('Filename:', image.filename)
    image_handler = ImageHandler(pil_image) # create ImageHandler

    date_and_coords = image_handler.get_date_and_coords() #get dat and coordinates from image
    print('Date and coords:', date_and_coords) """

    path = await s3.check_and_rename_file(str(group), filename) # rename file if it exists
    print('Path:', filename)
    filename = path.split('/')[-1] # get the filename from the path
    print('Filename:', filename)
    presigned = await s3.presign_file(path) # get presigned url for the file
    print('presigned', presigned)
    # insert into db
    if image_id is not None: # update existing image
        updated_image = images_collection.find_one_and_update({
            '_id': image_id
        },
        {'$set': {
            'filename': filename,
            'updated_at': datetime.now(timezone.utc)
        }},
        return_document=True
        )
    else: # insert new image
        inserted_image = images_collection.insert_one({
            'filename': filename,
            'data': {},
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
            'group': group
        })
        print('Inserted image:', inserted_image)
    return {
        '_id': str(inserted_image.inserted_id) if image_id is None else str(updated_image['_id']),
        'filename': path,
        'presigned_url': presigned['presigned_url'],
        'type': presigned['type'],
    }


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
async def delete_group(group_id:str, db=Depends(connect_to_db), s3=Depends(setup_s3_handler)):
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
        s3.delete_image(str(group_id), image['filename']) # delete image from s3


    #delete images in group
    image_collection.delete_many({'group': group_id})

    return result

################### IMAGES ###################
# Add images to an existing group
@app.post("/images/{group_id}", response_description="Upload images to a group")
async def prepare_upload_images_to_group(group_id: str, images: list[str]=Body(None, embed=True), db=Depends(connect_to_db), s3=Depends(setup_s3_handler)):
    group_id = ObjectId(group_id) # convert to ObjectId
    print('Group:', group_id)

    group_collection = db.get_collection('image_groups')
    if (group := group_collection.find_one({'_id': group_id})) is not None:
        # add images to group
        if len(images) > 0:
            image_data = await add_images_to_group(str(group_id), images, db, s3)
        else:
            image_data = []
        print('Image data:', image_data)
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
async def edit_image(image_id: str, data:Annotated[UpdateImageData, Body(embed=True)], db=Depends(connect_to_db), s3=Depends(setup_s3_handler)):
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
        elif 'group' in data:
            #move image
            print('move image prepare')
            s3.move_image(str(data_result['group']), data['group'], data_result['filename'])

    else:
        data_result = image_collection.find_one({'_id': image_id})

    return data_result

@app.patch("/images/{image_id}/file", response_description="Edit an image of that id")
async def replace_image(image_id: str, image:str=Body(..., embed=True), db=Depends(connect_to_db), s3=Depends(setup_s3_handler)):
    print('Image:', image)
    image_id = ObjectId(image_id) # Convert to ObjectId
    image_collection = db.get_collection('images')

    #print('Filename:', image.filename)

    old_image = image_collection.find_one({'_id': image_id},{'filename': 1, 'group': 1}) # get old image and group
    if old_image is not None: # if old image exists delete it from s3
        await s3.delete_image(str(old_image['group']), old_image['filename'])
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Image with that ID not found")

    image_result = await prepare_upload_single_image(old_image['group'], image, image_collection, s3)

    return image_result

@app.delete("/images/{image_id}", response_model=ImageData, response_model_by_alias=False, response_model_exclude_none=True,
            response_description="Delete an image")
async def delete_image(image_id:str, db=Depends(connect_to_db), s3=Depends(setup_s3_handler)):
    image_id = ObjectId(image_id) # convert to ObjectId

    image_collection = db.get_collection('images')

    result = image_collection.find_one_and_delete({'_id': image_id})
    if result is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Image with that ID not found")
    print('delete_image, prepare', result)
    s3.delete_image(result['group'], result['filename']) # delete image from s3

    return result

# Process S3 image after upload, called by handler in response to S3 event
async def process_s3_image(event, context):
    print('Processing S3 image...')
    print('Event:', event)
    s3_event = event["Records"][0]["s3"]
    #bucket_name = s3_event['bucket']['name']
    key = s3_event['object']['key']

    path_parts = key.split('/')
    if (len(path_parts) == 3):
        group_id = path_parts[1]
        filename = path_parts[-1]

        # Depends won't work here because not in FastAPI context
        dbo = connect_to_db()
        print(dbo)
        print(type(dbo))
        db = next(dbo) # Get db connection
        print(db)
        s3 = S3Handler() # Get S3 handler

        processed_image = await s3.process_image(group_id, filename)

        image_collection = db.get_collection('images')
        image = image_collection.find_one_and_update({
            'filename': filename,
            'group': ObjectId(group_id)
        },
        {'$set': {
            'data': processed_image['data'],
            'updated_at': datetime.now(timezone.utc)
        }},
        return_document=True)
        print(image)
        if 'data' in image and 'DateTime' in image['data']:
            image['data']['DateTime'] = image['data']['DateTime'].astimezone(timezone.utc).isoformat() # Convert DateTime to ISO format
        if 'data' in image and 'DateTimeOriginal' in image['data']:
            image['data']['DateTimeOriginal'] = image['data']['DateTimeOriginal'].astimezone(timezone.utc).isoformat() # Convert DateTime to ISO format
        results = {
            'id': str(image['_id']),
            'filename': image['filename'],
            'group': str(image['group']),
            'data': image['data'],
            'files': processed_image['files']
        }
        print('Processed image results:', results)
        return results
    else:
        return {'error':'Invalid S3 key format, Expecting "orginal/<group_id>/<filename>"'}
# This is the handler that AWS Lambda will call first, check event here
def handler(event, context):
    print('Event:', event)
    print('Context:', context)
    if event.get("Records") and event["Records"][0].get('eventSource') == 'aws:s3': # Check if the event is from S3
        # call the process s3 function
        loop = asyncio.new_event_loop()
        t = loop.run_until_complete(process_s3_image(event, context))
        return t


    asgi_handler = Mangum(app=app, lifespan="off") # Use Mangum to handle AWS Lambda events
    response = asgi_handler(event, context) # Call the instance with the event arguments

    return response

#handler = Mangum(app=app, lifespan="off") # Use Mangum to handle AWS Lambda events

if __name__ == "__main__":
   import uvicorn
   uvicorn.run(app, host="0.0.0.0", port=8080)

#docker build -t bandpics-image-api .
#docker run -d --name image_api_dev -p 8000:8000 bandpics-image-api