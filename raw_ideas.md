I want to really redesign the app and I basically want it to have two modes: 
1.	One mode will be the Live mode where it pulls the data live and it compares it against our targets.
2.	The second mode will be a replay mode where I select a date and time and then when I push play it plays from that point as if it was live so that I can track it.
I also am going to pull data from the Speed V2 spreadsheet that we referenced earlier. We will be using the following tabs. 
The first tab will be the HSB2 cheat sheet and the second tab will be the LAB2 cheat sheet.
Another aspect of the app that I want is the ability to choose the configuration. I'm sailing on the F50 boat and we have: 
•	a different configuration of wings
•	a different configuration of foils
•	a different configuration of jibs
I want the ability to choose: 
1.	the foils, which will be either the HSB2 foils or the LAB2 foils (these are the two different cheat sheets)
2.	the wing, which will be choosing between the 24 m wing, the 27 m wing, and the 18 m wing
3.	I will also select the rudders and these will be either the LARW rudders or the HSRW rudders. The final configuration to choose from will be either the big jib or the small jib.
Once I have selected the configuration within the app, it will then go and pull the targets out of the cheatsheets in the Excel spreadsheet. The way this spreadsheet is structured, it basically has a bunch of numbers at the top of the table. It's got all the variables that I want: 
•	True wind speed (TWS)
•	True wind angle (TWA)
•	Boat speed (BSP)
•	Drop (DRP), which is the amount of cant we have when we drop
•	Cant, which is obviously the cant that they are running
•	RH target, which is the ride height target (that's the elevation of the boat above the water)
•	Rudders, which is the rudder averages (there are two rows there and you'll just select based on the configuration selection)
•	Wing settings, which is the wing camber, the wing twist, the wing clew position, and the wing rotation
•	Jib section, which, based on the configuration, will either have big jib or small jib
The jib section will track the jib track, the jib sheet load, and the jib cano load. Another point to make is that these rows are not completely filled out so if we are using a specific target and the box is empty just don't display a target but keep tracking the metric. For example if we haven't noted the wing position I still want you to pull the data and show the wing rotation. It will just display the orange and it will just have no target. The other thing to note is that, based on the configuration, the targets will change based on the true wind speed. As the true wind speed goes up or down the targets that we are tracking shift. For example if I look at the HSB2 18m upwind configuration with the HSRW rudders and the big jib, if it is 25 true wind speed I will use the top row and it would be the true wind angle, the boat speed, the drop, cant, etc. If we're sailing along and the true wind speed increases and then we get to 30 true wind speed (in km/h), as we get to that point the targets will shift based on that row. I don't want you to interpolate. I want you to round up or down to the nearest true wind speed so my true wind speed goes up and down in increments of 2.5 kph. I just want you to select the targets that are closest to that true wind speed. 
The other thing we need is the tolerance of the target. We're pulling all the targets from the spreadsheet but I haven't set a tolerance to know if we're going to be in the green, the red, or the orange. That's what I want to set within the app. I just want to have all of the metrics and then all of the tolerances. Based on the targets that it pulls from the spreadsheet, it just needs tolerance for that metric. I also want you to have a bit of critical thinking on this. For example: 
•	With boat speed if I am above my target boat speed, that will always be green.
•	With true wind angle if I am sailing above my true wind angle target, that will always also be green.
•	If I'm going downwind and I am deeper than my true wind angle, that will always be green.
•	In VMG if I'm above VMG, it will always be green, etc.
Whereas all the other metrics there can have a tolerance plus and minus. If I'm too far away from that tolerance it is red. If I'm within that tolerance it's green and if I'm on the fringe of that tolerance it is amber or orange. 
Another issue that I'm currently having on the app is that it is very hard to read a lot of the writing especially in the settings section. I want you to just completely review the code and make sure everything is easy to look at. It's got a really nice user interface. I don't mind if you change the user interface quite a lot because at the moment it's not very good so make sure the app just works really well super quickly.
When I'm looking at my targets and my traffic light system, I want to basically have all of it fit on one page. The way it is now manages to fit on one page. The targets that we use, like I said earlier, I only want the targets within the cheat sheet. Based on the current code the extra targets that I have, you can get rid of those. I just want the targets within the cheat sheet.
And obviously the other feature that we need to keep within the app is the detection of the upwind and the downwind. The targets for the upwind and downwind will change as per the cheat sheets and as per the data.
