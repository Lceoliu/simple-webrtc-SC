document.addEventListener("DOMContentLoaded", () => {
	const videoTableBody = document
		.getElementById("videoTable")
		.getElementsByTagName("tbody")[0];

	// Function to create and return a new row for the video table
	function createVideoRow(clientId, bitrate, ice_state, port_num) {
		const row = document.createElement("tr");

		const portNumCell = document.createElement("td");
		portNumCell.textContent = port_num;
		row.appendChild(portNumCell);

		const clientIdCell = document.createElement("td");
		clientIdCell.textContent = clientId;
		row.appendChild(clientIdCell);

		const videoCell = document.createElement("td");
		const img = document.createElement("img");
		videoCell.appendChild(img);
		row.appendChild(videoCell);

		const bitrateCell = document.createElement("td");
		bitrateCell.textContent = bitrate;
		bitrateCell.id = "bps";
		row.appendChild(bitrateCell);

		const iceStateCell = document.createElement("td");
		iceStateCell.textContent = ice_state;
		iceStateCell.id = "state";
		row.appendChild(iceStateCell);

		videoTableBody.appendChild(row);
		return img;
	}

	function handleIncomingVideoData(
		clientId,
		videoData,
		bitrate,
		ice_state,
		port_num
	) {
		let img = document.getElementById(clientId);
		if (!img) {
			img = createVideoRow(clientId, bitrate, ice_state, port_num);
			img.id = clientId;
		}
		img.src = "data:image/jpeg;base64," + videoData;
		const row = img.closest("tr");

		const bpsElement = row.querySelector('[id^="bps"]');
		const stateElement = row.querySelector('[id^="state"]');

		if (!bpsElement || !stateElement) {
			console.error("bps or state element not found in the same row");
			return;
		}

		bpsElement.textContent = bitrate;
		stateElement.textContent = ice_state;
	}

	async function fetchVideoData() {
		const response = await fetch("/stats");
		if (!response.ok) {
			throw new Error("Network response was not ok");
		}
		return await response.json();
	}

	async function displayVideos() {
		while (true) {
			try {
				const videoData = await fetchVideoData();
				for (const clientId in videoData) {
					const clientData = videoData[clientId];
					handleIncomingVideoData(
						clientData.client_id,
						clientData.video,
						clientData.bps,
						clientData.ice_connection_state,
						clientData.port_num
					);
				}
			} catch (error) {
				console.error("Error fetching video data:", error);
			}
		}
	}

	displayVideos();
});
