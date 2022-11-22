# S'mores slack app

A slack app to build connections in a remote work environment - When working remotely, it's hard to build connections and have casual chats as one would have in office. S'mores solves it by matching people from a slack channel when added to one for random 1-1s so that people can have casual chats outside work meetings.

## Installing
---
### Hosting

This app currently isn't available on general slack app directory, you can create your own instance by hosting it yourself. It is built to be run on Heroku using the Procfile and you'd need a Redis and Postgres instance. From your slack account hosting the app, you'd need to set the environment variables defined in `template.env`. 

### Using it once installed in a workspace

To enable it in a channel, follow these instructions:
1. Create a channel (or use an existing one) from which the people will be paired
2. Add the S'mores App bot to the channel - This can be done by at-mentioning the bot user from that channel: `@Smores`
3. Run the slash command `/smores enable`

To disable, run the following command from the channel: `/smores disable`

The intros are sent every 2 weeks currently on Mondays (To be made configurable in future). To force the pairs to be created and sent immediately you can run the following command: 
```
/smores force_chat
``` 
*Note: The next pair will be sent on the Monday 2 weeks after this date - so if this command was run on Thursday then the next conversation will be sent on 2 weeks + 3 days.*

## Contributing
---
All contributions are welcome and I will try to review your PRs in a timely manner. Looking for contributions on adding more tests, completing TODO tasks in the code, work on reported issues in the Issues tab and improving code quality.

Like using the app? Consider buying me a coffee and support development by donating:

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donate_LG.gif)](https://www.paypal.com/donate/?business=ARLRHPV9XXAMW&no_recurring=0&item_name=For+supporting+S%27mores+app+development&currency_code=CAD)