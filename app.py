from flask import Flask, render_template, redirect, send_file, send_from_directory
import os

app = Flask(__name__)


@app.route('/')
def index():
    projects = [
        {
            'name': 'AQI Display', 
            'description': 'A menu bar app for monitoring air quality',
            'image': '/static/images/pic1.png',
            'link': 'AQIdisplay'
            },
        {
            'name': 'Financial Data Analysis ', 
            'description': 'Python, Pandas, Parquets',
            'image': '/static/images/pic2.png',
            'link': '/findata'
            },
        {
            'name': 'Food Good', 
            'description': 'iOS app recommending recipes based on ingredients',
            'image': '/static/images/recipe_recommends.png',
            'link': '/foodgood'            
            },
        {
            'name': 'Visual Studies', 
            'description': 'Processing, Python, Matplotlib',
            'image': '/static/images/test5.jpeg',
            'link': '/artwork'   
            }
    ]
    return render_template('index.html', projects=projects)

@app.route('/AQIdisplay')
def aqidisplay():
    return render_template('aqidisplay.html')

@app.route('/foodgood')
def foodgood():
    return render_template('foodgood.html')

@app.route('/findata')
def projects():
    return render_template('jupyter1.html')

@app.route('/artwork')
def artwork():
    return render_template('jupyter2.html')

@app.route('/artnotebook')
def artnotebook():
    return render_template('jupyter3.html')

@app.route('/oa_project')
def oa_project():
    return redirect('https://github.com/jimmmmmmmmmmmy')

@app.route('/resume')
def resume():
    return render_template('resume.html')

@app.route('/pdfs/Resume.pdf')
def serve_resume_pdf():
    return send_from_directory(
        'static/pdfs', 
        'Resume.pdf')

@app.route('/downloads/AQIDisplay.zip')
def download_file():
    try:
        return send_from_directory(
            'static/downloads',
            'AQIDisplay.zip',
            as_attachment=True
        )
    except Exception as e:
        return "Sorry, the download is currently unavailable."

if __name__ == '__main__':
    app.run(debug=True)