# Bandpics: Image API (Python version)
This is an API for the Bandpics project, it primarily deals with images including extracting their Exif data related to locations and time, and managing the images themselves.

The Python version (I might eventually make a Node.js version) uses FastAPI, Pydantic, MongoDB and Pillow so far.

This API has these concerns around images:
- The uploading and management of images in S3
- The extraction of GPS and Time data from images
- The management of the data about the images and groups

## How it's structured
There's 2 collections in the MongoDB dataase:
- `images`: Which contains some metadata about the images, including their filename, GPS coordinates, time they were taken, and the image group they belong to.
- `image_groups`: Which represents a group of images, and includes a name and description. They'll eventually be associated with an event.

## The API
The API endpoints are CRUD endpoints for images and image groups.

### Images

- `GET /images/{image_id}`
    Get a single image metadata by its ID.

- `POST /images`
    Upload a new image with metadata.

- `PATCH /images/{image_id}`
    Update metadata for an image.

- `PATCH /images/{image_id}/file`
    Replace the image file with an uploaded image and update extracted exif data.

- `DELETE /images/{image_id}`
    Delete an image.

### Image Groups

- `GET /image_groups/{group_id}`
    Get a single image group by its ID, and output the metadata of the images in that group.

- `POST /image_groups`
    Upload images and create a new image group.

- `PATCH /image_groups/{group_id}`
    Update an image group, it's name and description mainly.

- `DELETE /image_groups/{group_id}`
    Delete an image group.

## S3
The images are stored on S3 with the following key paths:
- {group_id}/original/{filename} which contains the original unmodified image with the GPS data, these images might be removed later and are not meant to be used in the gallery
- {group_id}/fullsize/{filename} which is the resized and modified image, the GPS data has removed here. It's meant to be the fullsize images in the gallery
- {group_id}/thumb/{filename} which is the thumbnail used for the gallery, there's no GPS data in this one.

## Things done
- Added a basic FastAPI app with CRUD endpoints for images and image groups.
- Added schemas for images and image groups using Pydantic.
- Added a class image_handler for extracting the Exif data from images.
- Added unit tests for image_handler and integrations tests for the API endpoints.
- Integrated S3 for the storing and management of the image files. (Changes to implementation incoming)
- Implementing a docker image for the API
- Added automated testing with Github Actions
- Added push Docker image to ECR with Github Actions
- Added update AWS Lambda function with Github Actions

## To Do
- Change upload process to use S3 presigned URLs and remove the need to upload the image file in the request body.
- Implement S3 triggers to the image processing, which would include extract Exif data and resizing the images.
- Add authentication for the API, using JWT and Incognito.
- Possibly adding logging depending on where it's deployed.
- Possbily having methods to remove GPS data of the images if needed.