import App from './App.svelte';
import { importResponse, importPostResponse } from './fetch-isolation/import/response';
import { uploadResponse } from './fetch-isolation/upload/response';
import { storeResponse } from './fetch-isolation/store/response';
import { cacheResponse, getMessageResponse, deleteMessageResponse } from './fetch-isolation/cache/response';
import { sendResponse, sendSingleMessageResponse } from './fetch-isolation/send/response';

// import fetchMock from 'fetch-mock';

// fetchMock
//   .mock('*', 200);
import { createServer } from "miragejs"

// http://localhost:3280/api/v1/web/guest/util/import

createServer({
  routes() {
    
        // click link import URL 
        this.get("/api/v1/web/guest/util/import", () => importResponse)
        // click button Import in import URL
        this.post("/api/v1/web/guest/util/upload", () => uploadResponse)
        this.post("/api/v1/web/guest/util/import", () => importPostResponse)
        this.post("/api/v1/web/guest/util/store", () => storeResponse)
        // click link Send Messages
        this.get("/api/v1/web/guest/util/cache?scan=message:*", () => cacheResponse)
        // select messages and click on Send button
        this.get("/api/v1/web/guest/util/cache?message:AAAAAA00A00A000A:1", () => getMessageResponse)
        this.post("/api/v1/web/guest/util/send", () => sendResponse)
        this.delete("/api/v1/web/guest/util/cache?message:AAAAAA00A00A000A:1", () => deleteMessageResponse)
        // send single message
        this.post("/api/v1/web/guest/util/send", () => sendSingleMessageResponse)
  },
})

const app = new App({
	target: document.body
});

export default app;