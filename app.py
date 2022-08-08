from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from flask_wtf.csrf import CSRFProtect
from datetime import datetime
from bson import ObjectId
import os
import uuid

from azureproject import mongodb
from requests import RequestException

app = Flask(__name__, static_folder='static')
csrf = CSRFProtect(app)

# WEBSITE_HOSTNAME exists only in production environment
if not 'WEBSITE_HOSTNAME' in os.environ:
   # local development, where we'll use environment variables
   print("Loading config.development.")
   app.config.from_object('azureproject.development')
else:
   # production
   print("Loading config.production.")
   app.config.from_object('azureproject.production')


@app.route('/', methods=['GET'])
def index():
    print('Request for index page received')

    collection = mongodb.get_collection()
    results_restaurant_cursor = collection.find({"type" : "restaurant"})

    # Get the list of restaurants   
    restaurants_annotated = []
    for record in results_restaurant_cursor:
        # For each restaurant record, get the list of reviews so we can calculate average rating
        # print(record.get("name") + ", " + str(record.get("_id")))
        review_count, avg_rating = get_review_stats(str(record.get("_id")))
        new_record = record
        new_record.update({"review_count" : review_count, "avg_rating" : avg_rating, "id" : str(record.get("_id"))})  
        restaurants_annotated.append(new_record)        

    return render_template('index.html', restaurants=restaurants_annotated)

def get_review_stats(id):
    # print("Getting review stats for restaurant " + id)
    collection = mongodb.get_collection()
    review_count = collection.count_documents({"type" : "review", "restaurant" : ObjectId(id)})
    if review_count > 0:
        avg_rating_group = collection.aggregate([{"$match" : {"type" : "review", "restaurant" : ObjectId(id)}}, {"$group" : {"_id" : "$restaurant", "avg_rating" : {"$avg" : "$rating"}}}])
        avg_rating = avg_rating_group.next().get("avg_rating") 
    else:
        avg_rating = 0
    return review_count, avg_rating


@app.route('/<string:id>', methods=['GET'])
def details(id):
    return details(id,'')

def details(id, message):
    collection = mongodb.get_collection()
    print('Request for restaurant details page received')

    cursor = collection.find({"type" : "restaurant", "_id" : ObjectId(id)})
    restaurant = cursor.next()
    if cursor.retrieved != 0:
        review_count, avg_rating = get_review_stats(id)
        restaurant_annotated = restaurant
        restaurant_annotated.update({"review_count" : review_count, "avg_rating" : avg_rating, "id" : str(restaurant.get("_id"))})  

        # Get reviews for the restaurant.
        reviews_cursor = collection.find({"type" : "review", "restaurant" : ObjectId(id)})
    else:
        raise Http404("Restaurant not found")
    return render_template('details.html', restaurant=restaurant_annotated, reviews=reviews_cursor, message=message)

@app.route('/create', methods=['GET'])
def create_restaurant():
    print('Request for add restaurant page received')
    return render_template('create_restaurant.html')

@app.route('/add', methods=['POST'])
@csrf.exempt
def add_restaurant():
    try:
        name = request.values.get('restaurant_name')
        street_address = request.values.get('street_address')
        description = request.values.get('description')
        if (name == "" or description == ""):
            raise RequestException()
    except (KeyError, RequestException) as e:
        # Redisplay the restaurant entry form.
        return render_template('create_restaurant.html', 
            message='Restaurant not added. Include at least a restaurant name and description.')  
    else:
        collection = mongodb.get_collection()
        restaurant = mongodb.create_restaurant_record(name, street_address, description)
        id = collection.insert_one(restaurant).inserted_id

    return redirect(url_for('details', id=id))

@app.route('/review/<string:id>', methods=['POST'])
@csrf.exempt
def add_review(id):
    collection = mongodb.get_collection()
    cursor = collection.find({"type" : "restaurant", "_id" : ObjectId(id)})
    cursor.next()
    if cursor.retrieved == 0:
        raise Http404("Restaurant not found")

    try:
        user_name = request.values.get('user_name')
        rating = request.values.get('rating')
        review_text = request.values.get('review_text')
        if (user_name == "" or rating == None):
            raise RequestException()            
    except (KeyError, RequestException) as e:
        # Redisplay the details page
        return details(str(id), 'Review not added. Include at least a name and rating for review.')
    else:
        review_record = mongodb.create_review_record(id, user_name, rating, review_text)
        document_id_review = collection.insert_one(review_record).inserted_id
        print("Inserted review document with _id {}".format(document_id_review))                

    return redirect(url_for('details', id=id))

@app.context_processor
def utility_processor():
    def star_rating(id):
        collection = mongodb.get_collection()
        results_reviews_cursor = collection.find({"type" : "review", "restaurant" : ObjectId(id)})

        ratings = []
        review_count = 0;        
        for review in results_reviews_cursor:
            ratings += [review.get("rating")]
            review_count += 1

        avg_rating = round(sum(ratings)/len(ratings), 2) if ratings else 0
        stars_percent = round((avg_rating / 5.0) * 100) if review_count > 0 else 0
        return {'avg_rating': avg_rating, 'review_count': review_count, 'stars_percent': stars_percent}

    return dict(star_rating=star_rating)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
   app.run()