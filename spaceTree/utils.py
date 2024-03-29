import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from torch_geometric.utils import remove_self_loops
from tqdm import tqdm
import seaborn as sns
import matplotlib.pyplot as plt
from sparsemax import Sparsemax

def get_results(pred, data, node_encoder_rev, node_encoder_ct, node_encoder_cl, activation = None):
    pred_clone = pred[:,:data.num_classes_clone-1]
    pred_cell_type = pred[:,data.num_classes_clone-1:]
    if activation == None:
        pred_clone = pred_clone.detach().cpu().numpy()
        pred_cell_type = pred_cell_type.detach().cpu().numpy()
    elif activation == "sparsemax":
        pred_clone = Sparsemax(dim = 1)(pred_clone).detach().cpu().numpy()
        pred_cell_type = Sparsemax(dim = 1)(pred_cell_type).detach().cpu().numpy()
    elif activation == "softmax":
        pred_clone = np.exp(pred_clone.detach().cpu().numpy())
        pred_cell_type = np.exp(pred_cell_type.detach().cpu().numpy())
    cells_hold_out =[node_encoder_rev[x.item()] for x in data.hold_out]
    clone_res = pd.DataFrame(pred_clone[data.hold_out.detach().cpu().numpy()], index = cells_hold_out)
    clone_res.columns =[node_encoder_cl[x] for x in clone_res.columns]
    ct_res = pd.DataFrame(pred_cell_type[data.hold_out.detach().cpu().numpy()], index = cells_hold_out)
    ct_res.columns = [node_encoder_ct[x] for x in ct_res.columns]
    return(clone_res,ct_res)



def rotate_90_degrees_clockwise(matrix):
    min_x, min_y = matrix.min(axis=0)
    max_x, max_y = matrix.max(axis=0)
    
    w = max_x - min_x
    h = max_y - min_y
    # Translate to center
    matrix[:, 0] -= w/2
    matrix[:, 1] -= h/2

    # Rotate
    rotated = np.zeros_like(matrix)
    rotated[:, 0] = -matrix[:, 1]
    rotated[:, 1] = matrix[:, 0]

    # Translate back
    rotated[:, 0] += h/2
    rotated[:, 1] += w/2
    
    return rotated

def get_attention_visium(w,node_encoder_rev, data,coordinates):
    edges = w[0]
    weight = w[1]
    edge, edge_weight = remove_self_loops(edges, weight)
    spatial_nodes = set(list(data.hold_out.cpu().numpy()))
    spatial_graph = {}
    for i in tqdm(range(edge.shape[1])):
        source = edge[0][i].item()
        target = edge[1][i].item()
        source_id = node_encoder_rev[source]
        target_id = node_encoder_rev[target]
        if target in spatial_nodes:
            if target_id not in spatial_graph:
                spatial_graph[target_id] = []
            if  source == target:
                spatial_graph[target_id].append((source_id,edge_weight[i].item(), "self"))
                
            elif source in spatial_nodes:
                spatial_graph[target_id].append((source_id,edge_weight[i].item(), "spatial"))
            else:
                spatial_graph[target_id].append((source_id,edge_weight[i].item(), "reference"))
    full_df = []
    for key in tqdm(spatial_graph):
        tmp = pd.DataFrame(spatial_graph[key], columns = ["source", "weight", "type"])
        tmp.drop_duplicates(inplace=True)
        tmp["target"] = key
        full_df.append(tmp)
    full_df = pd.concat(full_df)
    ds = []
    for tup in tqdm(full_df.itertuples()):
        if tup.type == "spatial":
            source = str(tup.source)
            target = str(tup.target)
            if source in coordinates.index and target in coordinates.index:
                source_coor = coordinates.loc[source].values
                target_coor = coordinates.loc[target].values
                dist = np.sum(np.abs(source_coor - target_coor))
                if dist == 2:
                    dist = "first_neighbour"
                elif dist == 4:
                    dist = "second_neighbour"
                elif dist == 0:
                    dist = "self"
            else:
                dist = "reference"
        else:
            dist = "reference"
        ds.append(dist)
    full_df["distance"] = ds



    full_df = full_df[["target","distance","weight"]].groupby(["target", "distance"]).sum().reset_index()
    full_df = full_df.set_index("target")
    sns.histplot(full_df, x = "weight", hue = "distance", bins = 50, log_scale = False)
    plt.show()

    full_df = full_df.pivot(columns = "distance", values = "weight")

    return(full_df)



def get_attention(w,node_encoder_rev, data,coordinates):
    edges = w[0]
    weight = w[1]
    edge, edge_weight = remove_self_loops(edges, weight)
    spatial_nodes = set(list(data.hold_out.cpu().numpy()))
    spatial_graph = {}
    for i in tqdm(range(edge.shape[1])):
        source = edge[0][i].item()
        target = edge[1][i].item()
        source_id = node_encoder_rev[source]
        target_id = node_encoder_rev[target]
        if target in spatial_nodes:
            if target_id not in spatial_graph:
                spatial_graph[target_id] = []
            if  source == target:
                spatial_graph[target_id].append((source_id,edge_weight[i].item(), "self"))
                
            elif source in spatial_nodes:
                spatial_graph[target_id].append((source_id,edge_weight[i].item(), "spatial"))
            else:
                spatial_graph[target_id].append((source_id,edge_weight[i].item(), "reference"))
    full_df = []
    for key in tqdm(spatial_graph):
        tmp = pd.DataFrame(spatial_graph[key], columns = ["source", "weight", "type"])
        tmp.drop_duplicates(inplace=True)
        tmp["target"] = key
        full_df.append(tmp)
    full_df = pd.concat(full_df)
    ds = []
    for tup in tqdm(full_df.itertuples()):
        if tup.type == "spatial":
            source = str(tup.source)
            target = str(tup.target)
            if source in coordinates.index and target in coordinates.index:
                source_coor = coordinates.loc[source].values
                target_coor = coordinates.loc[target].values
                dist = np.sum(np.abs(source_coor - target_coor))
            else:
                dist = 0
        else:
            dist = 0
        ds.append(dist)
    full_df["distance"] = ds
    spatial = full_df[full_df.type != "reference"]
    sc = full_df[full_df.type == "reference"]
    spatial["distance"] = pd.cut(spatial.distance,3, labels = ["short","medium","long"])
    sc["distance"] = "reference"
    full_df = pd.concat([sc,spatial])
    full_df = full_df[["target","distance","weight"]].groupby(["target", "distance"]).sum().reset_index()
    sns.histplot(full_df, x = "weight", hue = "distance", bins = 50, log_scale = False)
    plt.show()

    full_df = full_df.pivot(columns = "distance", values = "weight", index = "target")
    return(full_df)

def check_class_distributions(data, weight_clone, weight_type, norm_sim):
    num_class_train = data.y_clone[data.train_mask].unique().shape[0]
    num_class_total = len(data.y_clone.unique())
    assert num_class_total -1 == num_class_train, f"""Number of *clone* classes in training set {num_class_train} is not
    equal to total number of classes {num_class_total -1}"""
    assert num_class_total -1 == len(weight_clone), "Number of *clone* classes is not equal to number of weights"
    assert num_class_total -1 == norm_sim.shape[0], "Number of *clone* classes is not equal to number of similarity scores"

    num_class_train = data.y_type[data.train_mask].unique().shape[0]
    num_class_total = len(data.y_type.unique())
    assert num_class_total -1 == num_class_train, "Number of *type* classes in training set is not equal to total number of classes"

def compute_class_weights(y_train):
    """Calculate class weights based on the class sample count."""
    class_sample_count = np.array([len(np.where(y_train == t)[0]) for t in np.unique(y_train)])
    return 1. / class_sample_count

def plot_metrics(stored_metrics):
    extracted_clone = [metrics_dict["validation_acc_clone"].item() 
                        for metrics_dict in stored_metrics["val"] 
                        if "validation_acc_clone" in metrics_dict and torch.is_tensor(metrics_dict["validation_acc_clone"])]
    extracted_ct = [metrics_dict["validation_acc_ct"].item() 
                        for metrics_dict in stored_metrics["val"] 
                        if "validation_acc_ct" in metrics_dict and torch.is_tensor(metrics_dict["validation_acc_ct"])]
    plt.plot(extracted_clone, label = "clone")
    plt.plot(extracted_ct, label = "cell type")
    plt.legend()
    plt.show()


# class MyMetricsCallback(pl.Callback):
#     def __init__(self):
#         super().__init__()
#         self.train_metrics = []
#         self.val_metrics = []

#     def on_train_batch_end(self, trainer, pl_module, *args, **kwargs):
#         # Collect metrics logged in training_step
#         metrics = trainer.logged_metrics
#         self.train_metrics.append(metrics.copy())

#     def on_validation_batch_end(self, trainer, pl_module, *args, **kwargs):
#         # Collect metrics logged in validation_step
#         metrics = trainer.logged_metrics
#         self.val_metrics.append(metrics.copy())

#     def get_metrics(self):
#         return {
#             "train": self.train_metrics,
#             "val": self.val_metrics
#         }


