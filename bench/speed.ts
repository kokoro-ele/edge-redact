/** Single-thread speed of the CPU model on 10,000 code units of mixed zh/en text. node bench/speed.ts <model.erdm> */
import { readFileSync } from 'node:fs'
import { loadModel, predict } from '../src/model/cpu.ts'

const m = loadModel(readFileSync(process.argv[2] ?? 'models/zh-en-ds48-int4.erdm'))
const unit = '客户张伟反馈登录失败，手机号 138 0013 8000，log 里是 401 Unauthorized。Please email sarah.chen@example.com, order 7444494389. '
let text = ''
while (text.length < 10_000)
  text += unit
text = text.slice(0, 10_000)
predict(m, text.slice(0, 2000)) // warm up
const times: number[] = []
for (let i = 0; i < 5; i++) {
  const t0 = performance.now()
  predict(m, text)
  times.push(performance.now() - t0)
}
times.sort((a, b) => a - b)
console.log(`${m.header.name}: 10k units median ${times[2]!.toFixed(1)} ms (min ${times[0]!.toFixed(1)})`)
