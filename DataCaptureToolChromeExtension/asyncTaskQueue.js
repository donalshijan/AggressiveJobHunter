const asyncTaskQueue = [];

function queueAsyncTask(fn) {
// const task = fn();

  const task = Promise.resolve().then(fn);
  asyncTaskQueue.push(task);
  task.finally(() => {
    const idx = asyncTaskQueue.indexOf(task);
    if (idx !== -1) asyncTaskQueue.splice(idx, 1);
  });
  return task;
}

//queue tasks
// queueAsyncTask(() => pushCurrentPageCapture());

// wait for all tasks to finish
// await Promise.all(asyncTaskQueue);