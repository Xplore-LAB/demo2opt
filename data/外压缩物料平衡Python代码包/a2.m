function [fitresult, gof] = createFit(EGOX, FIC103AVG)
%CREATEFIT(EGOX,FIC103AVG)
%  创建一个拟合。
%
%  要进行 '无标题拟合 2' 拟合的数据:
%      X 输入: EGOX
%      Y 输出: FIC103AVG
%  输出:
%      fitresult: 表示拟合的拟合对象。
%      gof: 带有拟合优度信息的结构体。
%
%  另请参阅 FIT, CFIT, SFIT.

%  由 MATLAB 于 08-May-2026 17:46:39 自动生成


%% 拟合: '无标题拟合 2'。
[xData, yData] = prepareCurveData( EGOX, FIC103AVG );

% 设置 fittype 和选项。
ft = fittype( 'poly1' );
excludedPoints = excludedata( xData, yData, 'Indices', [988 989 990 991 992 2415 2509] );
opts = fitoptions( 'Method', 'LinearLeastSquares' );
opts.Exclude = excludedPoints;

% 对数据进行模型拟合。
[fitresult, gof] = fit( xData, yData, ft, opts );

% 绘制数据拟合图。
figure( 'Name', '无标题拟合 2' );
h = plot( fitresult, xData, yData, excludedPoints );
legend( h, 'FIC103AVG vs. EGOX', '已排除 FIC103AVG vs. EGOX', '无标题拟合 2', 'Location', 'NorthEast', 'Interpreter', 'none' );
% 为坐标区加标签
xlabel( 'EGOX', 'Interpreter', 'none' );
ylabel( 'FIC103AVG', 'Interpreter', 'none' );
grid on


