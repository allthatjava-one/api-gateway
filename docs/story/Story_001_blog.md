I want to make endpoing `/blogs` to get all blogs and `/blogs/{id}` to get a specific blog by its ID.

## Technologies used:
- Cloudflare D1 database for storing blog data.
- Cloudflare Workers for handling API requests.

## Data Structure
/blogs endpoint will return a list of blog objects, each containing the following fields:
'''
{
    slug: 'meme-generator-guide',
    title: 'Meme Generator Guide',
    description: 'Step-by-step guide and tips for creating memes with THRJ\'s Meme Generator.',
    thumbnail: 'https://thrjtech.com/screenshots/meme-generator/meme-generator004.png'
}
'''

/blogs/{id} endpoint will return a single blog object with the following fields and content is Markdown formatted string:
```
{
    slug: 'meme-generator-guide',
    title: 'Meme Generator Guide',
    content: 'Step-by-step guide and tips for creating memes with THRJ\'s Meme Generator.'
}
```

## Implementation Steps
1. Set up Cloudflare D1 database and create a table for blogs with appropriate fields (id, slug, title, description, thumbnail, content).
2. Create a Cloudflare Worker to handle API requests for the `/blogs` and `/blogs/{slug}` endpoints.
3. Implement the logic to fetch all blogs from the database and return them in the required format.
4. Implement the logic to fetch a single blog by its slug from the database and return it in the required format.
5. Test the endpoints to ensure they return the correct data and handle errors appropriately (e.g., blog not found).