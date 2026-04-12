I need to add new end point /api/v1/pdf-splitter to the API documentation. This endpoint will allow users to split a PDF file into multiple parts based on specified page ranges. The request will include the PDF file and the desired page ranges for splitting. The response will return the split PDF files as downloadable links.

# Tech Requirements
- The programming pattern should be similar to pdf-compressor: Take entire request body as input, pass it to the service layer, and return the response from the service layer directly.
- The service layer will handle the logic for splitting the PDF file based on the provided page ranges and will return the resulting split PDF files as downloadable links.

# API Endpoint: /api/v1/pdf-splitter

# As a Gateway API,
It shouldn't manipulate the request body or response body, but simply pass it through to the service layer. The Gateway API will receive the request, forward it to the service layer, and return the response from the service layer without any modifications.
- Environtment Variable "SERVICE_PDF_SPLIT_URL" will be provided from the environment, which contains the URL of the service layer responsible for handling the PDF splitting logic. The Gateway API will use this URL to forward the request to the appropriate service endpoint.

