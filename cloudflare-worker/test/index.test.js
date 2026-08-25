import assert from "node:assert/strict";
import test from "node:test";

import { localTimestamp, parseScheduledAt, selectDuePosts } from "../src/index.js";

test("Улаанбаатарын цагийг UTC+8-аар хөрвүүлнэ", () => {
  assert.equal(
    parseScheduledAt("2026-08-25 10:00"),
    Date.parse("2026-08-25T02:00:00Z"),
  );
  assert.equal(localTimestamp(new Date("2026-08-25T02:00:00Z")), "2026-08-25 10:00");
});

test("хугацаа болсон постыг сонгож, хэт хоцорсныг тусгаарлана", () => {
  const queue = [
    { id: 1, scheduled_at: "2026-08-25 10:00", status: "pending" },
    { id: 2, scheduled_at: "2026-08-25 07:00", status: "pending" },
    { id: 3, scheduled_at: "2026-08-25 13:00", status: "pending" },
    { id: 4, scheduled_at: "2026-08-25 09:00", status: "posted", posted_at: "2026-08-25 09:01" },
  ];
  const result = selectDuePosts(queue, Date.parse("2026-08-25T02:01:00Z"), {
    graceMinutes: 150,
    maxPostsPerRun: 3,
    maxPostsPerDay: 15,
  });
  assert.deepEqual(result.selected.map((post) => post.id), [1]);
  assert.deepEqual(result.stale.map((post) => post.id), [2]);
});

test("өдрийн хамгаалалтын хязгаарт хүрвэл шинэ пост claim хийхгүй", () => {
  const queue = [
    { id: 1, scheduled_at: "2026-08-25 10:00", status: "pending" },
    { id: 2, scheduled_at: "2026-08-25 08:30", status: "posted", posted_at: "2026-08-25 08:31" },
  ];
  const result = selectDuePosts(queue, Date.parse("2026-08-25T02:01:00Z"), {
    graceMinutes: 150,
    maxPostsPerRun: 3,
    maxPostsPerDay: 1,
  });
  assert.equal(result.selected.length, 0);
});
