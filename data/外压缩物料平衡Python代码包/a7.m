function [fitresult, gof] = createFit(FIC102AVG, HC1BAVG)
%CREATEFIT(FIC102AVG,HC1BAVG)
%  创建一个拟合。
%
%  要进行 '无标题拟合 7' 拟合的数据:
%      X 输入: FIC102AVG
%      Y 输出: HC1BAVG
%  输出:
%      fitresult: 表示拟合的拟合对象。
%      gof: 带有拟合优度信息的结构体。
%
%  另请参阅 FIT, CFIT, SFIT.

%  由 MATLAB 于 08-May-2026 17:47:00 自动生成


%% 拟合: '无标题拟合 7'。
[xData, yData] = prepareCurveData( FIC102AVG, HC1BAVG );

% 设置 fittype 和选项。
ft = fittype( 'poly1' );
excludedPoints = excludedata( xData, yData, 'Indices', [374 375 376 705 706 707 708 988 989 990 991 992 993 2410 2411 2412 2413 2414 2415 2416 2509] );
opts = fitoptions( 'Method', 'LinearLeastSquares' );
opts.Lower = [0.0018 -Inf];
opts.Exclude = excludedPoints;

% 对数据进行模型拟合。
[fitresult, gof] = fit( xData, yData, ft, opts );

% 绘制数据拟合图。
figure( 'Name', '无标题拟合 7' );
h = plot( fitresult, xData, yData, excludedPoints );
legend( h, 'HC1BAVG vs. FIC102AVG', '已排除 HC1BAVG vs. FIC102AVG', '无标题拟合 7', 'Location', 'NorthEast', 'Interpreter', 'none' );
% 为坐标区加标签
xlabel( 'FIC102AVG', 'Interpreter', 'none' );
ylabel( 'HC1BAVG', 'Interpreter', 'none' );
grid on


