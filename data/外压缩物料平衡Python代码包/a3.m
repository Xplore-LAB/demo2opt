function [fitresult, gof] = createFit(PAIR, FI702AVG)
%CREATEFIT(PAIR,FI702AVG)
%  创建一个拟合。
%
%  要进行 '无标题拟合 3' 拟合的数据:
%      X 输入: PAIR
%      Y 输出: FI702AVG
%  输出:
%      fitresult: 表示拟合的拟合对象。
%      gof: 带有拟合优度信息的结构体。
%
%  另请参阅 FIT, CFIT, SFIT.

%  由 MATLAB 于 08-May-2026 17:46:43 自动生成


%% 拟合: '无标题拟合 3'。
[xData, yData] = prepareCurveData( PAIR, FI702AVG );

% 设置 fittype 和选项。
ft = fittype( 'poly1' );
excludedPoints = excludedata( xData, yData, 'Indices', [987 988 989 990 991 992 993 994 995 996 997 998] );
opts = fitoptions( 'Method', 'LinearLeastSquares' );
opts.Exclude = excludedPoints;

% 对数据进行模型拟合。
[fitresult, gof] = fit( xData, yData, ft, opts );

% 绘制数据拟合图。
figure( 'Name', '无标题拟合 3' );
h = plot( fitresult, xData, yData, excludedPoints );
legend( h, 'FI702AVG vs. PAIR', '已排除 FI702AVG vs. PAIR', '无标题拟合 3', 'Location', 'NorthEast', 'Interpreter', 'none' );
% 为坐标区加标签
xlabel( 'PAIR', 'Interpreter', 'none' );
ylabel( 'FI702AVG', 'Interpreter', 'none' );
grid on


