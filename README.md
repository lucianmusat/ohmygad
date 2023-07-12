# OH MY GAD

### What is it?

Oh My Gad is a simple script that connects to my local trash collector company's site (GAD) and checks the next
trash collection dates. If one of the dates is tomorrow then it will start one of my Phillips Hue lights in the house
with an appropriate color, depending on the trash bin's colors that need to be collected.

### How does it work?

GAD does not seem to have an official API, but I query their website for the next collection dates by using my zip code. The script will do this and parse the HTML response to find the next collection dates.
It is scheduled to do this check every day at 8:00 AM.

### UPDATE
It no longer works, as GAD has changed their website to use redirects and browser localstorage data, in what I guess
is a way to prevent scraping. 
Maybe I will try to update the script to use a headless browser to get the data whenever I have some time.