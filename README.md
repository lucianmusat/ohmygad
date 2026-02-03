# OH MY GAD

### What is it?

Oh My Gad is a simple script that connects to my local trash collector company's site (GAD) and checks the next
trash collection dates. If one of the dates is tomorrow then it will start one of my Phillips Hue lights in the house
with an appropriate color, depending on the trash bin's colors that need to be collected.

### How does it work?

GAD used to have an official API, but for some reasone they stopped or hid it. I now query their website for the next collection dates by using my zip code. The script will do this and parse the HTML response to find the next collection dates.
It is scheduled externally (Airflow) and runs as a short-lived Kubernetes Job.

**UPDATE:** They also stopped allowing queries on their website based on zip code. Not only that, but they implemented client side redirects to stop me from using http requests directly. So I switched to a different approach. I now use a headless browser to open their website and get the next collection dates. For now this works, we'll see what they're gonna do next.

**UPDATE 2:** This one was a bit more tricky. They started to ignore the url arguments for the zip code and using the browser's local storage. It took me a while to figure that one out, as you would need to open the page with a new browser or incognito mode to see what is going on.

**UPDATE 3:** They keep changing the way they display the date, it seems to be in non-standard formats, so I have to make a parser function.

## Scheduling (Kubernetes + Airflow)

This project used to run continuously and schedule itself using the Python `schedule` library.

**Now it runs once and exits.** Scheduling is handled by Airflow, which triggers a short-lived Kubernetes **Job**.

