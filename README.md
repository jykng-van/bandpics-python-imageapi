# Bandpics: Image API (Python version)
This is an API for the Bandpics project, it primarily deals with images including extracting their Exif data related to locations and time, and managing the images themselves.

The Python version (I might eventually make a Node.js version) uses FastAPI, Pydantic, MongoDB and Pillow so far.

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
    Replace the image file with an upload image and update extracted exif data.

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

## Things done
- Added a basic FastAPI app with CRUD endpoints for images and image groups.
- Added schemas for images and image groups using Pydantic.
- Added a class image_handler for extracting the Exif data from images.
- Added unit tests for image_handler and integrations tests for the API endpoints.

## To Do
- Integrate S3 for storing the images.
- Add authentication for the API.
- Possibly adding logging depending on where it's deployed.
- Possibly making it AWS Lambda compatible.
- Possbily having methods to remove GPS data from images if needed.