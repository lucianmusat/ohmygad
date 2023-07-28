# OH MY GAD

### What is it?

Oh My Gad is a simple script that connects to my local trash collector company's site (GAD) and checks the next
trash collection dates. If one of the dates is tomorrow then it will start one of my Phillips Hue lights in the house
with an appropriate color, depending on the trash bin's colors that need to be collected.

### How does it work?

GAD does not seem to have an official API, but I query their website for the next collection dates by using my zip code. The script will do this and parse the HTML response to find the next collection dates.
It is scheduled to do this check every day at 8:00 AM.

**UPDATE:** They also stopped allowing queries on their website based on zip code. Not only that, but they implemented client side redirects to stop me from using http requests directly. So I switched to a different approach. I now use a headless browser to open their website and get the next collection dates. For now this works, we'll see what they're gonna do next.

### TODO:

- [ ] Add tests