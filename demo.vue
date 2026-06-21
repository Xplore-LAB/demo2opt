import React, { useState, useRef, useEffect, useCallback } from 'react';
import { 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, Brush, ReferenceArea
} from 'recharts';
import { 
  Activity, RefreshCw, Database, Upload, Clock, MousePointer2, Filter, Check, TrendingUp, TrendingDown, Minus, ZoomOut, RotateCcw
} from 'lucide-react';

const loadXLSX = () => {
  return new Promise((resolve) => {
    if (window.XLSX) {
      resolve(window.XLSX);
      return;
    }
    const script = document.createElement('script');
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js";
    script.onload = () => resolve(window.XLSX);
    document.head.appendChild(script);
  });
};

// 自定义图表悬浮提示
const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-slate-900/90 backdrop-blur-md border border-slate-700 p-4 rounded-2xl shadow-2xl pointer-events-none">
        <p className="text-slate-400 text-[11px] font-black uppercase tracking-wider mb-2">{label}</p>
        <div className="flex items-end gap-2">
          <p className="text-3xl font-black text-indigo-400">
            {Number(payload[0].value).toFixed(2)}
          </p>
          <span className="text-slate-500 font-bold text-sm mb-1">units</span>
        </div>
      </div>
    );
  }
  return null;
};

const App = () => {
  // 底层全量数据驻留内存
  const fullDataRef = useRef([]);
  
  // React State 用于渲染
  const [viewState, setViewState] = useState({
    chartData: [],
    stats: { max: 0, min: 0, avg: 0 },
    totalRows: 0,
    filteredRows: 0
  });

  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [rawArrayBuffer, setRawArrayBuffer] = useState(null);
  const [headers, setHeaders] = useState([]);
  const [showMapping, setShowMapping] = useState(false);
  const [mapping, setMapping] = useState({ time: '', value: '' });
  const [timeRange, setTimeRange] = useState('all');

  // 【核心交互增强】鼠标框选与缩放状态
  const [refAreaLeft, setRefAreaLeft] = useState(null);
  const [refAreaRight, setRefAreaRight] = useState(null);
  const [zoomHistory, setZoomHistory] = useState([]); // 记录放大历史，支持逐级撤销

  // 处理文件上传
  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setErrorMessage('');
    setIsProcessing(true);
    setZoomHistory([]); // 新文件清空缩放历史
    
    try {
      const XLSX = await loadXLSX();
      const reader = new FileReader();

      reader.onload = (e) => {
        try {
          const workbook = XLSX.read(e.target.result, { type: 'array', sheetRows: 1 });
          const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
          const range = XLSX.utils.sheet_to_json(firstSheet, { header: 1 });
          
          if (range && range.length > 0) {
            const foundHeaders = range[0].map((h, i) => h ? String(h).trim() : `Column_${i + 1}`);
            setHeaders(foundHeaders);
            setRawArrayBuffer(e.target.result);
            setMapping({ 
              time: foundHeaders[0], 
              value: foundHeaders.find(h => /705/i.test(h)) || foundHeaders[1] || foundHeaders[0] 
            });
            setShowMapping(true);
          }
        } catch (err) {
          setErrorMessage('读取表头失败');
        } finally {
          setIsProcessing(false);
        }
      };
      reader.readAsArrayBuffer(file);
    } catch (err) {
      setErrorMessage('库加载失败');
      setIsProcessing(false);
    }
  };

  // 根据范围计算图表视图，包含智能抽样 (Semantic Downsampling)
  const updateView = useCallback((rangeId, currentZoom) => {
    const fullData = fullDataRef.current;
    if (!fullData || fullData.length === 0) return;

    let filtered = fullData;
    let baseStartIndex = 0;
    
    // 1. 顶部基础时间范围截取
    if (rangeId !== 'all') {
      const rowMap = {
        '5m': 12 * 5, '30m': 12 * 30, '1h': 12 * 60, 
        '2h': 12 * 120, '5h': 12 * 300, '12h': 12 * 720, '24h': 12 * 1440 
      };
      const takeCount = rowMap[rangeId] || fullData.length;
      baseStartIndex = Math.max(0, fullData.length - takeCount);
    }

    // 2. 如果存在鼠标框选缩放，覆盖并精准截取该段高清数据
    if (currentZoom) {
      baseStartIndex = currentZoom[0];
      filtered = fullData.slice(currentZoom[0], currentZoom[1] + 1);
    } else {
      filtered = fullData.slice(baseStartIndex);
    }

    // 无损计算当前视图的统计指标
    let max = -Infinity, min = Infinity, sum = 0, validCount = 0;
    for (let i = 0; i < filtered.length; i++) {
      const val = filtered[i].v;
      if (val !== null) {
        if (val > max) max = val;
        if (val < min) min = val;
        sum += val;
        validCount++;
      }
    }

    const stats = {
      max: max === -Infinity ? 0 : max,
      min: min === Infinity ? 0 : min,
      avg: validCount === 0 ? 0 : (sum / validCount)
    };

    // 3. 高效降采样限制最大渲染点数，防止浏览器崩溃 (固定上限 1500 点)
    const maxPoints = 1500; 
    let sampled = [];
    
    if (filtered.length <= maxPoints) {
      // 数据够少，全量高清呈现
      sampled = filtered.map((d, i) => ({ 
        time: d.t, 
        raw: d.v, 
        _absIdx: baseStartIndex + i // 记录绝对坐标，用于框选时寻址
      }));
    } else {
      // 数据超量，执行跳步抽样
      const step = Math.max(1, Math.floor(filtered.length / maxPoints));
      for (let i = 0; i < filtered.length; i += step) {
        sampled.push({ 
          time: filtered[i].t, 
          raw: filtered[i].v,
          _absIdx: baseStartIndex + i 
        });
      }
    }

    setViewState({
      chartData: sampled,
      stats,
      totalRows: fullData.length,
      filteredRows: filtered.length
    });
  }, []);

  // 监听顶层过滤和缩放栈变化
  useEffect(() => {
    if (fullDataRef.current.length > 0) {
      const currentZoom = zoomHistory.length > 0 ? zoomHistory[zoomHistory.length - 1] : null;
      updateView(timeRange, currentZoom);
    }
  }, [timeRange, zoomHistory, updateView]);

  // 当外部时间范围按钮切换时，清空缩放历史
  const handleTimeRangeChange = (id) => {
    setZoomHistory([]);
    setTimeRange(id);
  };

  // 解析 Excel (基于 dense 模式防止内存溢出)
  const confirmMapping = async () => {
    if (!rawArrayBuffer) return;
    setIsProcessing(true);
    setErrorMessage('');

    requestAnimationFrame(async () => {
      try {
        const XLSX = await loadXLSX();
        
        const workbook = XLSX.read(rawArrayBuffer, { 
          type: 'array', 
          cellDates: false,
          dense: true,          // 二维数组模式
          cellFormula: false,   
          cellHTML: false,      
          cellStyles: false     
        });
        
        const worksheet = workbook.Sheets[workbook.SheetNames[0]];
        const timeColIdx = headers.indexOf(mapping.time);
        const valColIdx = headers.indexOf(mapping.value);

        const slimData = [];
        const sheetData = worksheet['!data'] || [];
        const maxRows = sheetData.length;
        let emptyCount = 0; 
        
        for (let r = 1; r < maxRows; r++) {
          const row = sheetData[r];
          
          if (!row || (!row[timeColIdx] && !row[valColIdx])) {
            emptyCount++;
            if (emptyCount > 200) break;
            continue;
          }
          emptyCount = 0;
          
          const timeCell = row[timeColIdx];
          const valCell = row[valColIdx];
          
          let v = valCell ? parseFloat(valCell.v) : null;
          if (v === 0 || isNaN(v)) v = null; 

          slimData.push({
            t: timeCell ? (timeCell.w ? String(timeCell.w) : String(timeCell.v)) : String(r),
            v: v
          });
        }

        fullDataRef.current = slimData;
        setShowMapping(false);
        setZoomHistory([]);
        updateView(timeRange, null);

      } catch (err) {
        setErrorMessage('解析失败: ' + err.message);
      } finally {
        setIsProcessing(false);
      }
    });
  };

  // ==== 鼠标框选缩放交互事件 ====
  const handleMouseDown = (e) => {
    if (e && e.activePayload && e.activePayload.length > 0) {
      setRefAreaLeft({ 
        absIdx: e.activePayload[0].payload._absIdx, 
        time: e.activePayload[0].payload.time 
      });
    }
  };

  const handleMouseMove = (e) => {
    if (refAreaLeft && e && e.activePayload && e.activePayload.length > 0) {
      setRefAreaRight({ 
        absIdx: e.activePayload[0].payload._absIdx, 
        time: e.activePayload[0].payload.time 
      });
    }
  };

  const handleMouseUp = () => {
    if (refAreaLeft && refAreaRight) {
      let leftIdx = refAreaLeft.absIdx;
      let rightIdx = refAreaRight.absIdx;
      
      // 确保从小到大
      if (leftIdx > rightIdx) {
        [leftIdx, rightIdx] = [rightIdx, leftIdx];
      }

      // 防止误触（选框数据量需大于 5 条才生效）
      if (rightIdx - leftIdx > 5) {
        setZoomHistory(prev => [...prev, [leftIdx, rightIdx]]);
      }
    }
    // 恢复状态
    setRefAreaLeft(null);
    setRefAreaRight(null);
  };

  const zoomOut = () => {
    setZoomHistory(prev => prev.slice(0, -1));
  };

  const zoomReset = () => {
    setZoomHistory([]);
  };

  return (
    <div className="flex flex-col h-screen bg-[#f8fafc] text-slate-800 font-sans select-none">
      <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-8 shrink-0 shadow-sm z-30">
        <div className="flex items-center gap-3">
          <div className="bg-indigo-600 p-2 rounded-xl shadow-lg shadow-indigo-200">
            <Activity className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-lg font-black text-slate-900 tracking-tight">AI705 智能交互监测系统</h1>
        </div>
        <div className="flex items-center gap-4">
          {errorMessage && <span className="text-red-500 font-bold text-sm bg-red-50 px-3 py-1 rounded-lg">{errorMessage}</span>}
          <label className="bg-slate-900 hover:bg-slate-800 text-white px-6 py-2.5 rounded-xl cursor-pointer transition-all font-bold text-sm flex items-center gap-2 shadow-lg shadow-slate-200">
            <Upload className="w-4 h-4" />
            加载新数据
            <input type="file" accept=".xlsx,.xls,.csv" onChange={handleFileUpload} className="hidden" />
          </label>
        </div>
      </header>

      <main className="flex-1 flex flex-col p-6 gap-6 overflow-hidden relative">
        {showMapping && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4">
            <div className="bg-white rounded-[32px] w-full max-w-md shadow-2xl border border-slate-100 overflow-hidden">
              <div className="p-8 bg-gradient-to-b from-slate-50 to-white border-b border-slate-100">
                <h2 className="text-xl font-black flex items-center gap-2 text-slate-800">
                  <Filter className="w-5 h-5 text-indigo-600" /> 数据流映射配置
                </h2>
                <p className="text-slate-500 text-xs mt-2 font-medium">请选择代表 AI705 监测值的列</p>
              </div>
              <div className="p-8 space-y-6">
                <div>
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3 block">目标分析列</label>
                  <div className="relative">
                    <select 
                      value={mapping.value} 
                      onChange={(e) => setMapping({...mapping, value: e.target.value})} 
                      className="w-full p-4 pl-5 bg-slate-50 border border-slate-200 rounded-2xl font-bold text-slate-700 appearance-none outline-none focus:ring-4 ring-indigo-500/20 focus:border-indigo-500 transition-all cursor-pointer"
                    >
                      {headers.map(h => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </div>
                </div>
                <button 
                  onClick={confirmMapping} 
                  disabled={isProcessing} 
                  className="w-full py-4 bg-indigo-600 text-white rounded-2xl font-black shadow-xl shadow-indigo-200 hover:bg-indigo-700 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {isProcessing ? <RefreshCw className="w-5 h-5 animate-spin" /> : '构建可视化视界'}
                </button>
              </div>
            </div>
          </div>
        )}

        {viewState.totalRows > 0 ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 shrink-0">
              <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 flex items-center justify-between group hover:border-indigo-200 transition-all">
                <div>
                  <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1 flex items-center gap-1">
                    <TrendingUp className="w-3 h-3 text-emerald-500" /> 峰值 Max
                  </p>
                  <p className="text-2xl font-black text-slate-800">{viewState.stats.max.toFixed(2)}</p>
                </div>
              </div>
              <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 flex items-center justify-between group hover:border-indigo-200 transition-all">
                <div>
                  <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1 flex items-center gap-1">
                    <TrendingDown className="w-3 h-3 text-rose-500" /> 谷值 Min
                  </p>
                  <p className="text-2xl font-black text-slate-800">{viewState.stats.min.toFixed(2)}</p>
                </div>
              </div>
              <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 flex items-center justify-between group hover:border-indigo-200 transition-all">
                <div>
                  <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1 flex items-center gap-1">
                    <Minus className="w-3 h-3 text-indigo-500" /> 均值 Avg
                  </p>
                  <p className="text-2xl font-black text-slate-800">{viewState.stats.avg.toFixed(2)}</p>
                </div>
              </div>
              <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800 flex items-center justify-between text-white relative overflow-hidden">
                <div className="absolute right-0 top-0 opacity-10 transform translate-x-4 -translate-y-4">
                  <Database className="w-24 h-24" />
                </div>
                <div className="relative z-10">
                  <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">可视范围数据量</p>
                  <p className="text-2xl font-black">
                    {viewState.filteredRows.toLocaleString()} 
                    <span className="text-sm font-medium text-slate-400 ml-1">pts</span>
                  </p>
                </div>
              </div>
            </div>

            <section className="flex-1 bg-white p-6 md:p-8 rounded-[36px] shadow-sm border border-slate-100 flex flex-col min-h-0 relative">
              {/* 浮动的图表控制面板 */}
              <div className="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4 mb-8">
                <div className="flex items-center gap-3">
                  <div className="w-1.5 h-6 bg-indigo-600 rounded-full" />
                  <h3 className="text-lg font-black text-slate-800 flex items-center gap-2">
                    全景趋势时序分析 
                    <span className="text-xs bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-md font-bold">可在图表内按住鼠标拖拽进行高清放大</span>
                  </h3>
                </div>
                
                <div className="flex items-center gap-3">
                  {/* 放大的控制按钮 */}
                  {zoomHistory.length > 0 && (
                    <div className="flex gap-2 animate-fade-in-right mr-4 border-r border-slate-200 pr-4">
                      <button 
                        onClick={zoomOut}
                        className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl flex items-center gap-1.5 transition-all"
                      >
                        <ZoomOut className="w-3 h-3" /> 返回上层
                      </button>
                      <button 
                        onClick={zoomReset}
                        className="px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-600 text-xs font-bold rounded-xl flex items-center gap-1.5 transition-all"
                      >
                        <RotateCcw className="w-3 h-3" /> 还原全景
                      </button>
                    </div>
                  )}

                  <div className="flex flex-wrap gap-1.5 bg-slate-100/80 p-1.5 rounded-2xl border border-slate-200/50">
                    {[
                      {id: 'all', n: `全量(${viewState.totalRows})`}, {id: '5m', n: '5M'}, {id: '30m', n: '30M'}, 
                      {id: '1h', n: '1H'}, {id: '2h', n: '2H'}, {id: '5h', n: '5H'}, 
                      {id: '12h', n: '12H'}, {id: '24h', n: '24H'}
                    ].map(btn => (
                      <button 
                        key={btn.id} 
                        onClick={() => handleTimeRangeChange(btn.id)} 
                        className={`px-4 py-2 rounded-xl text-[11px] font-black transition-all ${
                          timeRange === btn.id && zoomHistory.length === 0
                            ? 'bg-white text-indigo-600 shadow-sm border border-slate-200/50' 
                            : 'text-slate-500 hover:text-slate-800 hover:bg-slate-200/50'
                        }`}
                      >
                        {btn.n}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="flex-1 min-h-0 w-full cursor-crosshair">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart 
                    data={viewState.chartData} 
                    margin={{ top: 10, right: 0, left: -20, bottom: 0 }}
                    onMouseDown={handleMouseDown}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={handleMouseUp} // 防止鼠标划出导致框选残留
                  >
                    <defs>
                      <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.4}/>
                        <stop offset="60%" stopColor="#818cf8" stopOpacity={0.1}/>
                        <stop offset="95%" stopColor="#ffffff" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="4 4" vertical={false} stroke="#f1f5f9" />
                    <XAxis 
                      dataKey="time" 
                      tick={{ fill: '#94a3b8', fontSize: 10, fontWeight: 700 }}
                      axisLine={false}
                      tickLine={false}
                      minTickGap={60}
                      dy={10}
                    />
                    <YAxis 
                      domain={['auto', 'auto']} 
                      tick={{ fill: '#94a3b8', fontSize: 10, fontWeight: 700 }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(val) => Number(val).toFixed(0)}
                    />
                    <Tooltip content={<CustomTooltip />} isAnimationActive={false} />
                    <Area 
                      type="monotone" 
                      dataKey="raw" 
                      stroke="#4f46e5" 
                      strokeWidth={2.5} 
                      fill="url(#areaGradient)" 
                      connectNulls={false} 
                      isAnimationActive={true} // 开启过渡动画，使得放大缩小时曲线变换更平滑
                      animationDuration={500}
                      activeDot={{ r: 6, fill: '#4f46e5', stroke: '#fff', strokeWidth: 3, shadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                    />
                    
                    {/* 框选高亮区域指示器 */}
                    {refAreaLeft && refAreaRight ? (
                      <ReferenceArea 
                        x1={refAreaLeft.time} 
                        x2={refAreaRight.time} 
                        strokeOpacity={0.3} 
                        fill="#4f46e5" 
                        fillOpacity={0.15} 
                      />
                    ) : null}

                    {/* 底部平移滑动条，不与框选缩放冲突 */}
                    <Brush 
                      dataKey="time" 
                      height={40} 
                      stroke="#cbd5e1" 
                      fill="transparent" 
                      travellerWidth={12}
                      gap={1}
                      className="mt-4 opacity-50 hover:opacity-100 transition-opacity"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center bg-white rounded-[36px] border-2 border-dashed border-slate-200">
            <div className="p-8 bg-indigo-50 rounded-full mb-6 relative">
              <Database className="w-12 h-12 text-indigo-200" />
              {isProcessing && <RefreshCw className="w-6 h-6 text-indigo-600 absolute bottom-0 right-0 animate-spin bg-white rounded-full p-1 shadow-md" />}
            </div>
            <p className="text-slate-400 font-black tracking-widest uppercase mb-2">
              {isProcessing ? '正在脱离主线程解析巨量数据...' : '等待 5s/行 监测流载入'}
            </p>
            <p className="text-slate-400 text-sm font-medium">请点击右上角按钮导入您的 Excel / CSV 数据源</p>
          </div>
        )}
      </main>

      <footer className="h-12 bg-white border-t border-slate-200 flex items-center justify-between px-8 text-[10px] font-black text-slate-400 uppercase tracking-widest shrink-0">
        <div className="flex gap-6">
          <span className="flex items-center gap-2 text-indigo-500"><Check className="w-4 h-4"/> 采样限制: max 1500pts / view</span>
          <span className="flex items-center gap-2"><MousePointer2 className="w-4 h-4"/> 支持鼠标框选高清重采样重绘</span>
        </div>
        <span>AI705 System Engine v6.0 (Semantic Zoom Edition)</span>
      </footer>
    </div>
  );
};

export default App;