import JsonApiRepo, { JsonApiPrimaryData } from './JsonApiRepo';

interface TaskMeta{
  done?: number
  total?: number
  phase?: string
  children?: any
}

interface TaskResultAttributes{
  taskId: string,
  taskName: string,
  taskArgs: string,
  taskKwargs: string,
  status: string,
  worker: string,
  contentType: string,
  contentEncoding: string,
  result: any,
  dateCreated: string,
  dateDone: string,
  traceback: string,
  taskMeta: TaskMeta
}

export interface TaskResult extends JsonApiPrimaryData {
  type: 'TaskResult',
  attributes: TaskResultAttributes
}

export interface TaskResults {
  [key: string]: TaskResult
}

class TaskResultRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/notify/task-results/', 'Ergebnisse');
  }
}

export default TaskResultRepo;
