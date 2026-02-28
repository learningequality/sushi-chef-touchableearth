# TE Sushi Chef

### Step 0: Installation

* [Install pip](https://pypi.python.org/pypi/pip) if you don't have it already.
* [Install Python3](https://www.python.org/downloads) if you don't have it already
* [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) if you don't have it already
* [Install FFmpeg](https://www.ffmpeg.org/download.html) if you don't have it already
* Open a terminal
* Run `git clone https://github.com/fle-internal/te-sushi-chef` 
  then `cd te-sushi-chef`
* Create a Python3 virtual env `virtualenv -p python3  venv`
  and activate it using `source venv/bin/activate`
* Run `pip install -r requirements.txt`
* Run python, and type `import imageio; imageio.plugins.freeimage.download()`

### Step 1: Obtaining an Authorization Token ###
You will need an authorization token to create a channel on Kolibri Studio. In order to obtain one:

1. Create an account on [Kolibri Studio](https://contentworkshop.learningequality.org/).
2. Navigate to the Tokens tab under your Settings page.
3. Copy the given authorization token (you will need this for later).

### Step 2: Running the chef ###
 * Open te-sushi-chef/chefdata/data.py
   * Change `SOURCE_DOMAIN` to your name (you only need to change this once)
   * Change `SOURCE_ID` to some unique identifier for the channel
 * For English channel run `./te_chef.py -v --reset --token=<token> lang=en`,
   replacing `<token>` with the token you copied earlier
 * For French channel run `./te_chef.py -v --reset --token=<token> lang=fr`,
   replacing `<token>` with the token you copied earlier

