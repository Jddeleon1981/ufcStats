from buildWeb import app

#checks if run was ran directly instead of being imported
if __name__ == '__main__':
    app.run(debug=True)
