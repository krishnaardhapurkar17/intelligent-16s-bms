% Export the supplied MATLAB regression ensembles to JSON trees for Python.
% Run from the repository root with MATLAB: matlab -batch "run('tools/export_matlab_ensembles.m')"

root = fileparts(fileparts(mfilename('fullpath')));
sourceDir = fullfile(root, 'AI models', 'battery_guardian_mk2-main', 'models');
featureFile = fullfile(root, 'AI models', 'battery_guardian_mk2-main', ...
    'battery_data', 'liion_features.csv');
outputDir = fullfile(root, 'models', 'ai');
if ~exist(outputDir, 'dir')
    mkdir(outputDir);
end

export_one('soh_liion_model.mat', 'soh_model', 'soh_metadata', ...
    {'cycle','Re','Rct','ambient_temperature','capacity_fade','delta_Capacity'}, ...
    'models/ai/soh_ensemble.json');
export_one('rul_liion_model.mat', 'rul_model', 'rul_metadata', ...
    {'cycle','SOH','Re','Rct','ambient_temperature','capacity_fade','delta_Capacity'}, ...
    'models/ai/rul_ensemble.json');

function export_one(matName, modelField, metadataField, features, relativeOutput)
    root = fileparts(fileparts(mfilename('fullpath')));
    sourceDir = fullfile(root, 'AI models', 'battery_guardian_mk2-main', 'models');
    outputPath = fullfile(root, relativeOutput);
    loaded = load(fullfile(sourceDir, matName));
    model = loaded.(modelField);
    metadata = loaded.(metadataField);
    allData = readtable(fullfile(root, 'AI models', 'battery_guardian_mk2-main', ...
        'battery_data', 'liion_features.csv'));
    X = table2array(allData(:, features));
    rowIds = unique(round(linspace(1, height(allData), min(128, height(allData)))));
    validationX = X(rowIds, :);
    validationY = predict(model, validationX);

    trees = cell(model.NumTrained, 1);
    weightedSum = zeros(size(validationY));
    weights = double(model.TrainedWeights(:));
    if isa(model, 'classreg.learning.regr.RegressionBaggedEnsemble')
        weights = weights ./ sum(weights);
    end
    for k = 1:model.NumTrained
        tree = model.Trained{k};
        treeData = struct();
        treeData.children = double(tree.Children);
        treeData.cut_predictor_index = double(tree.CutPredictorIndex(:));
        treeData.cut_point = double(tree.CutPoint(:));
        treeData.node_mean = double(tree.NodeMean(:));
        treeData.cut_type = cellstr(tree.CutType(:));
        trees{k} = treeData;
        weightedSum = weightedSum + weights(k) .* predict(tree, validationX);
    end

    export = struct();
    export.format_version = 1;
    export.model_type = class(model);
    export.method = char(model.Method);
    export.features = features;
    export.target = char(metadata.target);
    export.weights = weights;
    export.bias = mean(validationY - weightedSum);
    export.metadata = metadata;
    export.trees = trees;
    export.validation_features = validationX;
    export.validation_predictions = validationY;
    export.validation_bias_spread = max(abs((validationY - weightedSum) - export.bias));
    file = fopen(outputPath, 'w');
    assert(file >= 0, 'Could not open export path: %s', outputPath);
    cleanup = onCleanup(@() fclose(file));
    fwrite(file, jsonencode(export), 'char');
    fprintf('Exported %s: %d trees; validation residual spread %.12g\n', ...
        outputPath, model.NumTrained, export.validation_bias_spread);
end
