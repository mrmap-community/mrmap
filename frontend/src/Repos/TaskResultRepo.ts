import JsonApiRepo, { JsonApiDocument, JsonApiPrimaryData } from './JsonApiRepo';

interface TaskMeta{
  done?: number
  total?: number
  phase?: string
  children?: any
}

interface TaskResultAttributes{
  task_id: string,
  task_name: string,
  task_args: string,
  task_kwargs: string,
  status: string,
  worker: string,
  content_type: string,
  content_encoding: string,
  result: JsonApiDocument,
  date_created: string,
  date_done: string,
  traceback: string,
  task_meta: TaskMeta
}

export interface TaskResult extends JsonApiPrimaryData {
  type: 'TaskResult',
  attributes: TaskResultAttributes
}

export interface TaskResults {
  [key: string]: TaskResult
}

export class TaskResultRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/notify/task-results/', 'Ergebnisse');
  }
}

export default TaskResultRepo;
