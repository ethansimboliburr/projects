// Set up API key and base URL for TheSportsDB API (v1) 
// All API requests will use this BASE_URL
const API_KEY = "123";
const BASE_URL = `https://www.thesportsdb.com/api/v1/json/${API_KEY}`;

// HTML elements that will be manipulated with HTML
const searchBtn = document.getElementById("searchBtn");
const teamInput = document.getElementById("teamInput");
const eventsList = document.getElementById("eventsList");
const pastEventsList = document.getElementById("pastEventsList");
const playersList = document.getElementById("playersList");

// Code to run when the button is clicked
searchBtn.addEventListener("click", () => {
	const teamName = teamInput.value.trim();
	if (teamName) {
		getTeamData(teamName);
	}
});

// Show loading text
async function getTeamData(teamName) {
	eventsList.innerHTML = "<li>Loading upcoming games...</li>";
	pastEventsList.innerHTML = "<li>Loading past games...</li>";
	playersList.innerHTML = "<li>Loading roster...</li>";

	try {
		// Search team
		const searchRes = await fetch(`${BASE_URL}/searchteams.php?t=${teamName}`);
		const searchData = await searchRes.json();

		if (!searchData.teams) {
			eventsList.innerHTML = "<li>Team not found</li>";
			pastEventsList.innerHTML = "<li>Team not found</li>";
			playersList.innerHTML = "<li>Team not found</li>";
			return;
		}

		const team = searchData.teams[0];
		const teamId = team.idTeam;

		// Upcoming games
		// Fetch the next upcoming events for a specific team using its ID
		const eventsRes = await fetch(`${BASE_URL}/eventsnext.php?id=${teamId}`);
		const eventsData = await eventsRes.json();
		// Clear any previous events from the list in the HTML
		eventsList.innerHTML = "";
		
		// Check if the API returned any events
		if (eventsData.events) {
			// Loop through each event returned
			eventsData.events.forEach(event => {
				// Create a new list item element for this event
				const li = document.createElement("li");
				li.innerHTML = `
					<img src="${event.strThumb || 'https://via.placeholder.com/50'}" alt="Event Image">
					<div class="event-info">
						<strong class="event-name">${event.strEvent}</strong>
						<span class="event-date">${event.dateEvent} at ${event.strTime}</span>
					</div>
				`;
				// Add the list item to the events list in the HTML
				eventsList.appendChild(li);
			});
		} 
		
		else {
			// If no events are returned, display a placeholder message
			eventsList.innerHTML = "<li>No upcoming events found</li>";
		}

		// Past games
		// Fetch the last past events for a specific team using its ID
		const pastRes = await fetch(`${BASE_URL}/eventslast.php?id=${teamId}`);
		const pastData = await pastRes.json();
		// Clear any previous past events from the list in the HTML
		pastEventsList.innerHTML = "";
	
		// Check if the API returned any results
		if (pastData.results) {
			// Loop through each past event returned
			pastData.results.forEach(event => {
				// Create a new list item element for this past event
				const li = document.createElement("li");
				li.innerHTML = `
					<img src="${event.strThumb || 'https://via.placeholder.com/50'}" alt="Event Image">
					<div class="event-info">
						<strong class="event-name">${event.strEvent}</strong>
						<span class="event-date">${event.dateEvent}</span>
						<span class="event-score">Score: ${event.intHomeScore} - ${event.intAwayScore}</span>
					</div>
				`;
				// Add the list item to the past events list in the HTML
				pastEventsList.appendChild(li);
			});
		} 
		
		else {
			// If no past events are returned, display a placeholder message
			pastEventsList.innerHTML = "<li>No past events found</li>";
		}

		// Team roster
		// Fetch the full team roster for a specific team using its ID
		const playersRes = await fetch(`${BASE_URL}/lookup_all_players.php?id=${teamId}`);
		const playersData = await playersRes.json();
		// Clear any previous roster from the HTML
		playersList.innerHTML = "";
		
		// Check if the API returned player data
		if (playersData.player) {
			// Loop through each player returned
			playersData.player.forEach(player => {
				// Create a new list item element for this player
				const li = document.createElement("li");
				li.innerHTML = `
					<img src="${player.strThumb || 'https://via.placeholder.com/100'}" alt="${player.strPlayer}">
					<strong>${player.strPlayer}</strong>
					<p>${player.strPosition} — ${player.strNationality}</p>
				`;
				// Add the list item to the players list in the HTML
				playersList.appendChild(li);
			});
		} 
		
		else {
			// If no players are returned, display a placeholder message
			playersList.innerHTML = "<li>No players found</li>";
		}
	} 
	// Catch any errors 
	catch (err) {
		// Log the error to the console for debugging
		console.error(err);
		// Show an error message in each list on the page
		eventsList.innerHTML = "<li>Error fetching data</li>";
		pastEventsList.innerHTML = "<li>Error fetching data</li>";
		playersList.innerHTML = "<li>Error fetching data</li>";
	}
}
